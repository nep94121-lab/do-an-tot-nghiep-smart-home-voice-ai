# BÁO CÁO KHẢO SÁT & ĐIỀU TRA CHI TIẾT (SURVEY REPORT) — BUGS 6, 7, 8, 9, 12, 13

**Tác giả**: `teamwork_explorer_survey_3` (Explorer Subagent)  
**Nhiệm vụ**: Khảo sát mã nguồn, định vị nguyên nhân gốc rễ (Root Cause), xây dựng chiến lược kiểm thử TDD (Automated Tests) và đề xuất giải pháp kỹ thuật cho nhóm lỗi: Bug 6, Bug 7, Bug 8, Bug 9, Bug 12, Bug 13 theo `REAL_TEST_BUGS_20261105.md`.  
**Thời gian hoàn thành**: 2026-11-04T19:26:00Z  
**Dự án**: Smart Home Voice AI Simulator (`C:\Users\LENOVO\Desktop\đồ án tốt nghiệp`)  

---

## 1. OBSERVATION (QUAN SÁT THỰC NGHIỆM TRỰC TIẾP)

### 1.1. Bug 6: `/app` 3D thu gọn chỉ hiện placeholder nét đứt, không render Three.js
- **Đường dẫn tệp**:
  - `mobile_app/index.html` (dòng 181–193, dòng 666)
  - `simulator/static/css/mobile_app.css` (dòng 442–460)
  - `simulator/static/js/mobile_app.js` (không có lệnh gọi 3D nào)
  - `simulator/static/house3d.js` (dòng 181–220, hàm `window.SmartHome3D.init`)
- **Nội dung thực tế quan sát**:
  - Tại `mobile_app/index.html:187-192`:
    ```html
    <div class="overview-box preview-16-9" id="mobileOverviewBox" aria-label="Toàn cảnh ngôi nhà">
      <div style="text-align:center;">
        <div style="font-weight:600;font-size:15px;color:var(--text);margin-bottom:4px;">Mô hình Toàn cảnh 3D</div>
        <span class="muted" style="font-size:12px;">Xem trạng thái thiết bị 3D trong không gian</span>
      </div>
    </div>
    ```
  - Tại `simulator/static/css/mobile_app.css:442-459`: `.overview-box.preview-16-9` chỉ có viền nét đứt `border: 1px dashed #b9ccce; background: #f4f9f9;`.
  - Tại `mobile_app/index.html:666`: Chỉ nạp `<script src="/static/js/mobile_app.js"></script>`. Toàn bộ 3 thư viện 3D quan trọng gồm `/static/vendor/three.min.js`, `/static/vendor/GLTFLoader.js` và `/static/house3d.js` (vốn được nạp trên desktop `simulator/static/index.html:437-439`) **hoàn toàn không được nạp** trong `mobile_app/index.html`.
  - Trong `simulator/static/js/mobile_app.js`: Tìm kiếm chuỗi `SmartHome3D` và `mobileOverviewBox` trả về **0 kết quả**. Hàm khởi tạo 3D và hàm đẩy trạng thái thiết bị `window.SmartHome3D.updateDevices` / `updateSensors` không hề tồn tại trên mobile.

### 1.2. Bug 7: Tab Thiết bị `/app` chỉ có 4 thiết bị, thiếu điều hoà, còi, bơm (phải đủ 7)
- **Đường dẫn tệp**:
  - `simulator/static/js/mobile_app.js` (dòng 21, dòng 830–836)
  - `mobile_app/index.html` (dòng 255)
- **Nội dung thực tế quan sát**:
  - Tại `simulator/static/js/mobile_app.js:21`:
    ```javascript
    let showAllDevices = false;
    ```
  - Tại `simulator/static/js/mobile_app.js:830-836`:
    ```javascript
    const allDevices = snap.devices || [];
    const filtered = allDevices.filter(d => {
      const roomLabel = d.room || ROOM_NAMES[d.id] || 'Phòng khách';
      return selectedRoomFilter === 'all' || roomLabel === selectedRoomFilter;
    });
    const visibleDevices = showAllDevices ? filtered : filtered.slice(0, 4);
    ```
  - Vì `showAllDevices` mặc định là `false`, mảng thiết bị hiển thị trong `#devGrid` bị cắt cụt bằng `.slice(0, 4)`. Khi tải trang hoặc chuyển sang tab Thiết bị, người dùng chỉ thấy 4 thiết bị (`main_door`, `living_room_light`, `bedroom_light`, `fan`), trong khi 3 thiết bị chấp hành còn lại gồm `ac` (Điều hòa), `alarm_siren` (Còi báo động) và `garden_pump` (Bơm nước) bị ẩn hoàn toàn, buộc phải bấm nút "Xem tất cả" mới hiện.
  - Trên desktop `simulator/static/js/app.js:338-348`, hàm `renderDevices` hiển thị toàn bộ 7 thiết bị ngay lập tức mà không cắt bớt.

### 1.3. Bug 8: Tab Hồ sơ `/app`: nút Đăng xuất bị bottom nav che, dòng text thừa, đếm ngược Mời khách nhảy liên tục
- **Đường dẫn tệp**:
  - `mobile_app/index.html` (dòng 391, 450–454, 565)
  - `simulator/static/css/mobile_app.css` (dòng 25, 331–340)
  - `simulator/static/js/mobile_app.js` (dòng 1345–1350, 1431)
- **Nội dung thực tế quan sát**:
  - **Dòng chữ thừa**: `mobile_app/index.html:391` ghi cứng:
    ```html
    <p class="muted" style="font-size:12px;margin:12px 0;">Mỗi tab mở một màn riêng, không cuộn tới mục khác.</p>
    ```
  - **Nút Đăng xuất bị che**:
    - Nút `#mobileBtnLogout` nằm ở dòng 565 cuối cùng của `#tabViewAccount`:
      ```html
      <button type="button" class="btn secondary wide" id="mobileBtnLogout" onclick="submitMobileLogout()" style="margin-top:24px;">Đăng xuất</button>
      ```
    - Khung bottom nav `.bottom-nav` cố định ở đáy màn hình (`position: fixed; bottom: 0; z-index: 40;`) có chiều cao khoảng 60px kèm safe area.
    - Trên các trình duyệt di động như Samsung Internet có thanh toolbar đáy trình duyệt (~56px), tổng chiều cao che phủ ở đáy lên tới hơn 116px. `body` chỉ có padding đáy `calc(88px + env(safe-area-inset-bottom))`, khiến `#mobileBtnLogout` bị chìm dưới thanh điều hướng, người dùng không thể cuộn tới để bấm nếu không có khoảng đệm bổ sung.
  - **Đếm ngược Mời khách**:
    - `mobile_app/index.html:450-454` định nghĩa:
      ```html
      <details class="account-item" id="mobileDynamicQrCard">
        <summary>
          <span>Mời khách / Thành viên</span>
          <span id="mobileQrCountdown" class="muted">Đang chờ</span>
        </summary>
      ```
    - Trong `simulator/static/js/mobile_app.js:1431`, timer `setInterval(pollMobileSecurityAndTimers, 1000)` gọi `refreshMobileQr10s()` mỗi giây.
    - Tại dòng 1348: `cdEl.textContent = 'Còn ' + rem + 's';`.
    - Chuỗi `Còn 10s`, `Còn 9s`, `Còn 8s`... nhảy liên tục ngay trên thanh tiêu đề tóm tắt (summary) của danh mục tài khoản, khiến người dùng lầm tưởng quyền truy cập tài khoản hoặc mục menu sắp hết hạn trong vài giây.

### 1.4. Bug 9: Desktop `/`: Không có panel cảm biến nhiệt độ/độ ẩm/độ ẩm đất
- **Đường dẫn tệp**:
  - `simulator/static/index.html` (dòng 96–176)
  - `simulator/static/js/app.js` (dòng 461–471)
- **Nội dung thực tế quan sát**:
  - Trong `simulator/static/index.html`, hai cột giao diện (`.stack`) chỉ có 4 panel:
    1. Cột trái: `panel house` (3D Viewport) và `panel devices` (Thiết bị).
    2. Cột phải: `panel voice` (Giọng nói & Lệnh) và `panel schedule` (Lịch & Quy tắc).
    Hoàn toàn **không có panel cảm biến**.
  - Trong `simulator/static/js/app.js:461-470`:
    ```javascript
    const soil = snap.mqtt.soil_moisture_telemetry || {};
    const dht = snap.mqtt.dht11_telemetry || {};
    const soilLabel = document.getElementById("sensorSoilLabel") || document.getElementById("sensorSoilVal");
    if (soilLabel && soil.soil_moisture_pct !== undefined) {
      soilLabel.textContent = Math.round(soil.soil_moisture_pct) + "%";
    }
    const tempLabel = document.getElementById("sensorTempLabel") || document.getElementById("sensorDhtVal");
    if (tempLabel && dht.temp_c !== undefined) {
      tempLabel.textContent = Math.round(Number(dht.temp_c)) + "°C";
    }
    ```
    Các phần tử `sensorSoilLabel`, `sensorSoilVal`, `sensorTempLabel`, `sensorDhtVal` hoàn toàn **không tồn tại** trong `index.html`. Độ ẩm không khí (`humidity_pct`) thậm chí không được tìm phần tử để cập nhật. Giá trị không được kẹp (clamp) trong ngưỡng an toàn khi dữ liệu MQTT trả về sai lệch hoặc null.

### 1.5. Bug 12: QR scanner: Dòng "Đưa mã QR vào trong khung để quét" hiện 2 lần
- **Đường dẫn tệp**:
  - `mobile_app/index.html` (dòng 645–664)
  - `simulator/static/js/mobile_app.js` (dòng 687–692)
- **Nội dung thực tế quan sát**:
  - Tại `mobile_app/index.html:655`:
    ```html
    <p class="instruction" style="text-align:center;font-weight:500;margin:18px 0 4px;">Đưa mã QR vào trong khung để quét</p>
    <p class="muted" style="text-align:center;font-size:12px;">Quét mã đang hiển thị trên màn hình Chủ nhà.</p>
    <div class="actions" style="margin-top:auto;padding-top:12px;display:grid;gap:10px;">
      <button type="button" class="btn primary wide" id="mobileBtnStartCamera" onclick="startCameraScan()">Bật camera</button>
      <button type="button" class="btn secondary wide" id="mobileBtnManualCodeInput" onclick="manualQrCodeInput()">Nhập mã</button>
    </div>
    <p class="muted" id="mobileScannerStatus" style="text-align:center;font-size:12px;margin-top:14px;">Khi quét được mã: Đang kiểm tra mã…</p>
    ```
  - Tại `simulator/static/js/mobile_app.js:687-692`:
    ```javascript
    function openQrScanner() {
      const modal = document.getElementById('mobileQrScannerModal');
      const status = document.getElementById('mobileScannerStatus');
      if (modal) modal.hidden = false;
      if (status) status.textContent = 'Đưa mã QR vào trong khung để quét';
    }
    ```
  - Khi người dùng bấm mở modal quét QR, hàm `openQrScanner()` gán đè nội dung của `#mobileScannerStatus` thành `"Đưa mã QR vào trong khung để quét"`. Kết quả là trên cùng 1 màn hình modal, câu này xuất hiện 2 lần: 1 lần ở phía trên cụm nút (từ thẻ `p.instruction`) và 1 lần ở phía dưới cụm nút (từ thẻ `#mobileScannerStatus`).

### 1.6. Bug 13: `/logs` render ~300 dòng trên một trang dài
- **Đường dẫn tệp**:
  - `simulator/api/routes_logs.py` (dòng 112)
  - `simulator/static/logs.html` (dòng 93–126)
  - `simulator/static/js/logs.js` (dòng 25–30, dòng 81–122)
- **Nội dung thực tế quan sát**:
  - Tại `simulator/api/routes_logs.py:112`: Backend đọc `raw_logs = read_audit_logs(limit=300)` và trả về toàn bộ danh sách trong mảng `audit_logs`.
  - Tại `simulator/static/js/logs.js:86-121`:
    ```javascript
    lastLoadedLogs.forEach((item, idx) => {
      // Tạo 1 thẻ <tr> log-row
      // Tạo 1 thẻ <tr> log-detail-row
      // Tạo 1 thẻ <div> mobile-log-card
      logTbody.appendChild(tr);
      logTbody.appendChild(detailTr);
      mobileCards.appendChild(mCard);
    });
    ```
    Frontend duyệt toàn bộ 300 bản ghi, render trực tiếp hơn 600 thẻ `<tr>` và 300 thẻ card di động trên cùng một trang, gây tràn trang nghiêm trọng và kéo dài thanh cuộn.
  - Bộ lọc ngày `#logDateRange` trong `logs.html:95` hoàn toàn không được sử dụng trong hàm `loadDashboard()` của `logs.js:26`.
  - Không có bất kỳ nút phân trang (Pagination: Trang trước / Trang sau) hay nút "Xem thêm" (Load More) nào trong giao diện.

---

## 2. LOGIC CHAIN (CHUỖI LẬP LUẬN TỪ QUAN SÁT ĐẾN NGUYÊN NHÂN & GIẢI PHÁP)

### Logic 1 (Bug 6):
1. Thẻ `<div class="overview-box preview-16-9" id="mobileOverviewBox">` được định nghĩa trong `mobile_app/index.html:187` nhằm hiển thị mô hình nhà 3D rút gọn (16:9).
2. Thư viện `three.min.js`, `GLTFLoader.js` và `house3d.js` đã sẵn có trong `simulator/static/` và hoạt động hoàn hảo trên desktop.
3. Vì `mobile_app/index.html` chưa nạp 3 script này và `mobile_app.js` chưa gọi `window.SmartHome3D.init("mobileOverviewBox", null, ...)`, nên thẻ `#mobileOverviewBox` chỉ tồn tại dưới dạng khung viền nét đứt chứa chữ tĩnh.
4. **Giải pháp**:
   - Thêm 3 thẻ script trước `mobile_app.js` trong `mobile_app/index.html`.
   - Trong `mobile_app.js`, gọi `window.SmartHome3D.init("mobileOverviewBox", null, onToggleDevice)` khi khởi động app; và trong `renderState(snap)`, cập nhật `window.SmartHome3D.updateDevices` và `updateSensors`.
   - Giữ nguyên DOM ID `#mobileOverviewBox` và class `preview-16-9` để duy trì tương thích 100% với `tests/test_m8_mobile_screens.py`.

### Logic 2 (Bug 7):
1. Hệ thống nhà thông minh có tổng cộng 7 thiết bị vật lý (`main_door`, `living_room_light`, `bedroom_light`, `fan`, `ac`, `alarm_siren`, `garden_pump`).
2. Mảng `ICONS` và `ROOM_NAMES` trong `simulator/static/js/mobile_app.js:1-18` đã khai báo đầy đủ 7 thiết bị.
3. Dòng 835 của `mobile_app.js` sử dụng cờ `showAllDevices = false`, tự động cắt danh sách còn 4 phần tử bằng `.slice(0, 4)`.
4. **Giải pháp**:
   - Khởi tạo `showAllDevices = true` (hoặc hiển thị toàn bộ `filtered` khi ở tab Thiết bị).
   - Nút `#btnToggleShowAllDevices` chuyển nhãn sang "Thu gọn" (hoặc điều khiển ẩn/hiện nếu muốn), đảm bảo khi người dùng mở tab Thiết bị thì thấy ngay toàn bộ 7 thiết bị đồng bộ với desktop.

### Logic 3 (Bug 8):
1. Dòng chữ `Mỗi tab mở một màn riêng, không cuộn tới mục khác.` ở `mobile_app/index.html:391` là chú thích tạm từ giai đoạn phát triển Phase 2, cần bị xoá bỏ theo yêu cầu Bug 8.
2. Thanh điều hướng đáy `.bottom-nav` là thành phần cố định (`position: fixed; bottom: 0;`). Khi mở tab Tài khoản (`#tabViewAccount`), nút `#mobileBtnLogout` nằm ở đáy cùng của trang. Trên các thiết bị di động thực tế hoặc trình duyệt Samsung Internet có thanh tác vụ đáy, nút Đăng xuất bị đè lấp.
   - Thêm `padding-bottom: calc(56px + env(safe-area-inset-bottom))` vào `#tabViewAccount` hoặc `margin-bottom: calc(48px + env(safe-area-inset-bottom))` cho `#mobileBtnLogout`.
3. Nhãn `#mobileQrCountdown` hiển thị `Còn ${rem}s` ngay trong dòng `<summary>` làm rối mắt.
   - Định dạng lại nhãn rõ ràng: `Làm mới mã sau ${rem}s` hoặc `Mã QR tự đổi: ${rem}s` (hoặc badge riêng trong thân card QR), giữ nguyên DOM ID `#mobileQrCountdown`.

### Logic 4 (Bug 9):
1. Desktop `/` là trung tâm điều khiển chính của ngôi nhà, nhưng hiện tại chỉ hiển thị trạng thái cảm biến gián tiếp qua mô hình 3D (nếu di chuột vào pin), hoàn toàn thiếu panel số liệu trực quan trên dashboard.
2. Dữ liệu từ ESP8266 gửi về qua MQTT (`snap.mqtt.dht11_telemetry` và `soil_moisture_telemetry`) đã có sẵn trong `snap` của `app.js`.
3. Đoạn mã `app.js:463-470` đã có logic tìm kiếm `sensorSoilLabel` và `sensorTempLabel` nhưng trong `index.html` không có các phần tử này, và thiếu cảm biến độ ẩm không khí.
4. **Giải pháp**:
   - Bổ sung `<section class="panel sensors" id="secSensors" aria-labelledby="sensors-title">` trong `simulator/static/index.html`.
   - Hiển thị 3 chỉ số: Nhiệt độ trong nhà (°C), Độ ẩm không khí (%), Độ ẩm đất sân vườn (%).
   - Cài đặt hàm kẹp giá trị (clamp) trong `app.js`: Nhiệt độ [0, 60]°C (fallback 28.5°C), Độ ẩm [0, 100]% (fallback 65%), Độ ẩm đất [0, 100]% (fallback 62%) để ngăn các giá trị dị biệt/âm/vô cực.

### Logic 5 (Bug 12):
1. Trong modal `#mobileQrScannerModal`, thẻ `<p class="instruction">` ở dòng 655 đã hiển thị cố định câu hướng dẫn: `"Đưa mã QR vào trong khung để quét"`.
2. Hàm `openQrScanner()` trong `mobile_app.js:691` lại gán câu đó vào `#mobileScannerStatus` ở dòng 661.
3. Hai thẻ này cùng hiển thị đồng thời khi modal mở ra, tạo thành 2 câu giống hệt nhau.
4. **Giải pháp**: Trong `openQrScanner()`, đặt `#mobileScannerStatus` về trạng thái ban đầu `"Khi quét được mã: Đang kiểm tra mã…"` hoặc `"Sẵn sàng quét mã"`, không gán lặp lại câu của `p.instruction`.

### Logic 6 (Bug 13):
1. Hiện tại `/api/logs/dashboard` trả về 300 bản ghi nhật ký. Việc render 600 thẻ `<tr>` + 300 card di động làm chậm trình duyệt và tạo trang dài bất thường.
2. `tests/test_m3_challenger_api.py` và `tests/test_challenger_m5_interactions.py` kiểm định schema của `/api/logs/dashboard` (bắt buộc phải có khóa `audit_logs`).
3. **Giải pháp**:
   - Thực hiện phân trang phía client (Client-side Pagination) trong `simulator/static/js/logs.js`: mỗi trang hiển thị 20–25 bản ghi (`pageSize = 20`).
   - Thêm thanh điều khiển phân trang hoặc nút "Xem thêm sự kiện" (`#btnLogsLoadMore` và `#logsPaginationInfo`).
   - Kích hoạt bộ lọc theo ngày (`#logDateRange`: Tất cả, Hôm nay, 7 ngày qua) và lọc theo loại sự kiện / tìm kiếm từ khóa.
   - Che giấu mọi chuỗi gợi ý mật khẩu trong trường `detail` / `summary` (thay bằng `***` hoặc `[Đã ẩn thông tin bảo mật]`) để tuân thủ 100% nguyên tắc Zero-Leak của Bug 1 và Bug 13.

---

## 3. CAVEATS (GIỚI HẠN & ĐIỀU KIỆN BIÊN ĐÃ XEM XÉT)

1. **Bảo toàn 68 DOM IDs & Window Hooks**:
   - `test_challenger_m4_dom.py` quét toàn bộ DOM HTML và kiểm tra khớp 100% với các hàm export trên `window.*`.
   - `test_m8_mobile_screens.py` kiểm tra các ID cụ thể: `#mobileOverviewBox` (phải có class `preview-16-9`), `#btnToggleShowAllDevices`, `#mobileDisplayTemp`, `#mobileDisplaySoil`, `#mobileMainDoorStatus`, `#mobileAlarmSirenStatus`, `#mobileBtnLogout`, `#mobileQrCountdown`, `#mobileQrScannerModal`, `#mobileScanFrame`.
   - `test_challenger_m5_interactions.py` mock các ID trong `logs.html`: `#auditLogsTbody`, `#mobileLogCards`, `#logSearchInput`, `#logCategorySelect`, các pill `#btnFilterAll`, `#btnFilterDevice`, `#btnFilterVoice`, `#btnFilterSecurity`.
   - **Cam kết**: Tuyệt đối KHÔNG xoá hoặc đổi tên bất kỳ DOM ID nào trong số các ID trên.

2. **Chế độ 3D house3d.js**:
   - Mô hình 3D trên mobile chỉ cần góc nhìn "Toàn cảnh" (Overview), không cần thanh công cụ chuyển phòng phức tạp để đảm bảo hiệu năng và không chiếm dụng diện tích màn hình điện thoại.
   - WebGL context cần được khởi tạo an toàn: nếu trình duyệt mobile không hỗ trợ WebGL hoặc THREE chưa sẵn sàng, giữ fallback hiển thị ảnh/khung hợp lý mà không làm sập ứng dụng.

3. **Bảo mật Zero-Leak**:
   - Trong quá trình khảo sát và hiển thị logs, tuyệt đối không in mật khẩu mặc định hoặc mã OTP ra console/báo cáo.

---

## 4. CONCLUSION (KẾT LUẬN & ĐỀ XUẤT BẢN VÁ KỸ THUẬT)

### Bảng Tổng Hợp Vị Trí Sửa & Giải Pháp Chi Tiết:

| Bug | Tệp Mã Nguồn | Vị Trí Dòng | Hành Động Kỹ Thuật Chi Tiết |
|---|---|---|---|
| **Bug 6** | `mobile_app/index.html` | 187–192, 666 | Nạp `three.min.js`, `GLTFLoader.js`, `house3d.js`. Giữ nguyên `#mobileOverviewBox` (preview-16-9). |
| | `simulator/static/js/mobile_app.js` | `initMobileApp`, `renderState` | Gọi `window.SmartHome3D.init("mobileOverviewBox", null, ...)` và đồng bộ `updateDevices` / `updateSensors`. |
| | `simulator/static/css/mobile_app.css` | 443–459 | Bỏ viền nét đứt khi 3D canvas đã mount, căn giữa 16:9 sắc nét. |
| **Bug 7** | `simulator/static/js/mobile_app.js` | 21, 835 | Đổi `let showAllDevices = true;` để hiển thị đủ 7 thiết bị ngay từ đầu. |
| | `mobile_app/index.html` | 255 | Đồng bộ nhãn nút `#btnToggleShowAllDevices` sang "Thu gọn" khi đang mở đủ 7 thiết bị. |
| **Bug 8** | `mobile_app/index.html` | 391 | Xóa bỏ dòng `Mỗi tab mở một màn riêng, không cuộn tới mục khác.` |
| | `simulator/static/css/mobile_app.css` | 25, 435 | Tăng padding đáy cho `#tabViewAccount`: `padding-bottom: calc(64px + env(safe-area-inset-bottom))`. |
| | `simulator/static/js/mobile_app.js` | 1348 | Đổi chuỗi hiển thị `#mobileQrCountdown` thành `Đổi mã sau ${rem}s` để làm rõ ngữ nghĩa chu kỳ TOTP. |
| **Bug 9** | `simulator/static/index.html` | Cột trái (sau devices) | Bổ sung `<section class="panel sensors" id="secSensors">` với 3 ô Nhiệt độ, Độ ẩm, Độ ẩm đất. |
| | `simulator/static/js/app.js` | 461–471 | Cập nhật `sensorTempVal`, `sensorHumVal`, `sensorSoilVal` kèm hàm clamp giá trị hợp lý. |
| | `simulator/static/css/style.css` | Section `.panel.sensors` | Thêm style grid cảm biến gọn gàng, thanh lịch cho desktop. |
| **Bug 12**| `simulator/static/js/mobile_app.js` | 691 | Xóa dòng gán đè `status.textContent = 'Đưa mã QR vào trong khung để quét';` trong `openQrScanner()`. |
| **Bug 13**| `simulator/static/logs.html` | 124–126 | Thêm thanh phân trang `#logsPagination` (Trang trước, Trang sau, Thông tin số dòng). |
| | `simulator/static/js/logs.js` | 25–122 | Cài đặt phân trang client-side (`pageSize = 20`), lọc theo ngày `#logDateRange`, che giấu mật khẩu trong log detail. |

---

## 5. VERIFICATION METHOD (PHƯƠNG PHÁP KIỂM TRA ĐỘC LẬP & TDD TESTS)

### 5.1. Chiến Lược Kiểm Thử TDD Tự Động (TDD Test Strategy)
Một file test kiểm thử hồi quy mới `tests/test_p4_survey3_bugs.py` sẽ được thiết lập với 6 test case độc lập:

1. **`test_bug6_mobile_house3d_rendered`**:
   - Đọc `mobile_app/index.html`, kiểm tra sự hiện diện của `three.min.js`, `GLTFLoader.js` và `house3d.js`.
   - Phân tích cú pháp AST/nội dung của `mobile_app.js`, kiểm tra lệnh gọi `SmartHome3D.init("mobileOverviewBox", ...)`.
   - Khởi chạy headless browser (Playwright) hoặc node-vm mock: xác nhận phần tử `<canvas>` được chèn thành công bên trong `#mobileOverviewBox`.
2. **`test_bug7_mobile_devices_tab_shows_all_7_devices`**:
   - Truyền snapshot 7 thiết bị vào hàm `renderState(snap)` của `mobile_app.js`.
   - Kiểm tra số lượng thẻ con `.dev-row` trong `#devGrid`: phải bằng đúng 7 (bao gồm đủ `ac`, `alarm_siren`, `garden_pump`).
3. **`test_bug8_mobile_account_safe_area_and_countdown`**:
   - Kiểm tra nội dung `mobile_app/index.html`: chuỗi `"Mỗi tab mở một màn riêng"` **hoàn toàn biến mất**.
   - Kiểm tra CSS của `#tabViewAccount` / `#mobileBtnLogout`: có khoảng đệm tối thiểu $\ge 48\text{px}$ hoặc safe-area padding.
   - Kiểm tra format chuỗi gán vào `#mobileQrCountdown`: không chứa chuỗi cộc lốc `"Còn Ns"`, phải thể hiện rõ bản chất làm mới mã QR (`"Đổi mã sau"` hoặc `"Làm mới mã sau"`).
4. **`test_bug9_desktop_sensor_panel_and_clamping`**:
   - Phân tích `simulator/static/index.html`: xác nhận tồn tại panel `#secSensors` chứa các ID cảm biến nhiệt độ, độ ẩm, độ ẩm đất.
   - Kiểm tra logic trong `app.js`: gửi dữ liệu giả lập dị biệt (`temp_c = -999`, `humidity_pct = 999`), kiểm tra giá trị hiển thị trên DOM phải được clamp chặt chẽ trong khoảng hợp lệ [0, 60] và [0, 100].
5. **`test_bug12_qr_scanner_no_duplicate_instruction`**:
   - Gọi hàm `openQrScanner()` trong môi trường DOM mock.
   - Đếm số lần xuất hiện của chuỗi `"Đưa mã QR vào trong khung để quét"` trong toàn bộ nội dung của `#mobileQrScannerModal`: **chỉ được phép bằng đúng 1** (nằm ở `p.instruction`, `#mobileScannerStatus` không được lặp lại).
6. **`test_bug13_logs_pagination_and_filter`**:
   - Mock dữ liệu trả về 300 dòng nhật ký từ `/api/logs/dashboard`.
   - Gọi `loadDashboard()`: số lượng hàng `<tr>` hiển thị trong `#auditLogsTbody` tại trang đầu tiên phải là $\le 25$ dòng (không tràn 300 dòng).
   - Kiểm tra sự tồn tại của các nút điều hướng phân trang (`#btnPrevPage`, `#btnNextPage` hoặc `#btnLogsLoadMore`).

### 5.2. Lệnh Chạy Kiểm Thử Độc Lập
```powershell
# Chạy suite kiểm tra DOM & Mobile hiện tại
python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp

# Chạy suite TDD mới cho Phase 4 Survey 3
python -X utf8 -m pytest tests/test_p4_survey3_bugs.py --basetemp=.pytest_tmp

# Dọn dẹp thư mục tạm
if (Test-Path .pytest_tmp) { Remove-Item -Recurse -Force .pytest_tmp }
```

### 5.3. Điều Kiện Bác Bỏ (Invalidation Conditions)
Báo cáo và giải pháp sẽ bị coi là thất bại nếu:
- Bất kỳ DOM ID nào trong danh mục 68 DOM IDs bị xóa bỏ hoặc đổi tên.
- `house3d.js` trên desktop bị thay đổi concept hoặc lỗi WebGL context.
- `/logs` làm vỡ cấu trúc Dual-Key JSON của `/api/logs/dashboard` gây fail `test_m3_challenger_api.py`.
- Tệp sinh ra vi phạm mã hóa UTF-8 BOM hoặc chứa ký tự xuống dòng CRLF (`\r\n`).
