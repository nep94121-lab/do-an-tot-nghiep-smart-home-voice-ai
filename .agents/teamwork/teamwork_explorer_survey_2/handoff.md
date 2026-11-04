# Báo Cáo Khảo Sát & Phân Tích Chuyên Sâu (Survey Report)
**Tác giả:** teamwork_explorer_survey_2  
**Mục tiêu:** Khảo sát, truy vết nguyên nhân gốc rễ và xây dựng chiến lược kiểm thử TDD cho 4 lỗi: Bug 3, Bug 10, Bug 11, Bug 14 trong `REAL_TEST_BUGS_20261105.md`.

---

## 1. Observation (Bằng chứng quan sát trực tiếp)

### Bug 3: WebSocket lỗi trên Vercel production, banner mâu thuẫn header pill, resource 404
- **Tệp nguồn:** [`simulator/static/js/app.js`](file:///C:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/static/js/app.js#L811-L841)
  - Tại dòng 811–829 trong hàm `connectWebSocket()`:
    ```javascript
    ws.onclose = () => {
      fetch("/api/state")
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((snap) => {
          updateConnectionUI(true);
          applySnapshot(snap);
        })
        .catch(() => {
          updateConnectionUI(false);
        });

      wsRetryCount = Math.min(WS_MAX_RETRIES, wsRetryCount + 1);
      showWsReconnectBanner(wsRetryCount, WS_MAX_RETRIES);

      if (wsRetryCount < WS_MAX_RETRIES) {
        if (wsReconnectTimer) clearTimeout(wsReconnectTimer);
        wsReconnectTimer = setTimeout(connectWebSocket, 4000);
      }
    };
    ```
    Quan sát: Khi `ws.onclose` được kích hoạt (luôn xảy ra trên Vercel Serverless do không hỗ trợ persistent WebSocket kết nối dài), lời gọi `fetch("/api/state")` chạy thành công (HTTP 200 OK) và gọi `updateConnectionUI(true)` khiến chấm trạng thái `#connDot` đổi sang màu xanh và `#connText` hiện `"Đã kết nối"`. Tuy nhiên, ngay bên dưới, lệnh `showWsReconnectBanner(wsRetryCount, WS_MAX_RETRIES)` luôn luôn được thực thi vô điều kiện, làm hiện thanh banner `#wsReconnectBanner` màu cam vàng thông báo `"Mất kết nối thời gian thực tới ngôi nhà. Đang kết nối lại (lần 1/5)…"` rồi tiến tới `"Chưa khôi phục kết nối. Thử lại để cập nhật trạng thái."`.
  - Tại dòng 832–841 (`pollRestStateFallback`):
    ```javascript
    function pollRestStateFallback() {
      if (ws && ws.readyState === WebSocket.OPEN) return;
      fetch("/api/state")
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((snap) => {
          updateConnectionUI(true);
          applySnapshot(snap);
        })
        .catch(() => {});
    }
    ```
    Quan sát: Khi polling HTTP `/api/state` định kỳ 4s hoạt động bình thường, hàm này không hề gọi `hideWsReconnectBanner()`, dẫn tới việc banner lỗi tiếp tục nằm nguyên trên giao diện mặc dù dữ liệu snapshot vẫn đổ về bình thường.
  - Về lỗi Resource 404 trong console:
    - Trong [`simulator/static/sw.js`](file:///C:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/static/sw.js#L20): Mảng `SHELL_ASSETS` chứa `'/favicon.ico'`. Khi Service Worker cài đặt, `cache.add('/favicon.ico')` thực hiện fetch URL này.
    - Trong [`simulator/static/offline.html`](file:///C:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/static/offline.html#L185): Có lệnh `fetch('/favicon.ico', { method: 'HEAD', cache: 'no-store' })`.
    - Trong [`vercel.json`](file:///C:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/vercel.json#L14-L37): Danh sách `routes` không hề có route cho `/favicon.ico`. Do đó mọi request trình duyệt tới `/favicon.ico` đều rơi vào catch-all 404 ở dòng 36: `{ "src": "^/(.*)$", "status": 404, "dest": "/simulator/static/404.html" }` và ghi nhận HTTP 404 đỏ trong DevTools console.
    - Trên hệ thống tệp đĩa, tệp `simulator/static/favicon.ico` hoàn toàn chưa tồn tại.

---

### Bug 10: Bật/tắt đèn chậm, nhãn bị trống và phụ đề bị cắt thành "Đã bột"
- **Tệp nguồn:** [`simulator/static/js/app.js`](file:///C:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/static/js/app.js#L241-L347)
  - Tại dòng 241–261 (`toggleDeviceById`):
    ```javascript
    function toggleDeviceById(devId) {
      const dev = latestDevicesMap[devId];
      if (!dev) return;
      const isOn = dev.state === "ON" || dev.state === "OPEN";
      const action = dev.type === "door" ? (isOn ? "close" : "open") : isOn ? "turn_off" : "turn_on";
      const roleVal = roleSelect && roleSelect.value ? roleSelect.value : "";
      if (ws && ws.readyState === WebSocket.OPEN) {
        sendWs({ type: "manual_toggle", device_id: devId, action, role: roleVal });
      } else {
        fetch("/api/device", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device_id: devId, action, source: "MANUAL_UI" }),
        })
          .then((r) => r.json())
          .then((data) => {
            if (data && data.snapshot) applySnapshot(data.snapshot);
          })
          .catch(() => {});
      }
    }
    ```
    Quan sát: Khi người dùng bấm công tắc, hoàn toàn KHÔNG có cập nhật lạc quan (Optimistic UI). Giao diện đứng yên chờ đợi phản hồi từ mạng/serverless (trễ từ 300ms tới hơn 1s).
  - Tại dòng 279–282 (`renderDevices`):
    ```javascript
    function renderDevices(devices) {
      if (!devicesGrid || devicesGrid === noopEl) return;
      devicesGrid.innerHTML = "";
      latestDevicesMap = {};
    ```
    Quan sát: Mỗi khi cập nhật trạng thái thiết bị, hàm `renderDevices` xóa trắng toàn bộ DOM bằng `devicesGrid.innerHTML = ""` rồi render lại từ đầu. Khi luồng xử lý hoặc dữ liệu snapshot có độ trễ/rỗng tạm thời, thẻ thiết bị biến mất hoặc nhãn bị trống (empty label flash).
  - Tại dòng 263–277 (`getDeviceRoomLabel`):
    `roomText` được ghép từ chuỗi `${room} · ${st}` (ví dụ: `"Phòng khách · Đang bật"`).
    Trong [`simulator/static/css/style.css`](file:///C:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/static/css/style.css#L587-L606):
    `.device-list` chia 2 cột (`grid-template-columns: repeat(2, minmax(0, 1fr))`). Độ rộng khả dụng cho `.device-copy` chỉ khoảng 60px–80px. Chuỗi `"Phòng khách · Đang bật"` quá dài, bị xuống dòng và chữ `"bật"` bị mép thẻ hoặc thuộc tính overflow cắt xén đúng vào phần dấu tiếng Việt (`ậ`), khiến người dùng nhìn thấy bị xén/lỗi chính tả thành `"Đã bột"`.
  - Trong [`simulator/static/js/mobile_app.js`](file:///C:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/static/js/mobile_app.js#L853-L864): Thao tác click thẻ thiết bị cũng gọi `await fetch('/api/device')` trước rồi mới gọi `renderState(data.snapshot)`, không hề có optimistic UI.

---

### Bug 11: Sheet ghi âm hiện "Đang thu âm" khi popup quyền mic còn chờ; thiếu modal quyền mic
- **Tệp nguồn:** [`mobile_app/index.html`](file:///C:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/mobile_app/index.html#L592-L630) và [`simulator/static/js/mobile_app.js`](file:///C:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/static/js/mobile_app.js#L550-L630)
  - Trong `mobile_app/index.html`:
    Tại dòng 597: `<h2 id="mobileVoiceSheetTitle" style="margin:0;font-size:18px;">Đang thu âm</h2>`.
    Quan sát: Toàn bộ tệp `mobile_app/index.html` KHÔNG HỀ CÓ phần tử hộp thoại quyền micro (mic permission modal), trong khi ở bản desktop `simulator/static/index.html` đã có sẵn `#micPermissionModal`.
  - Trong `simulator/static/js/mobile_app.js`:
    Tại dòng 559 trong `openVoiceBottomSheet()`:
    ```javascript
    if (title) title.textContent = 'Đang thu âm';
    startVoiceSheetRecording();
    ```
    Và tại dòng 602–628 trong `startVoiceSheetRecording()`:
    ```javascript
    try {
      if (typeof navigator !== 'undefined' && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        voiceSheetStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      }
    } catch (e) {}

    const bars = document.querySelectorAll('#mobileVoiceVolumeBars i');
    ...
    animateBars();

    voiceSheetTimer = setInterval(() => {
      voiceSheetSec++;
      ...
    }, 1000);
    ```
    Quan sát:
    1. Khi gọi `openVoiceBottomSheet()`, tiêu đề ngay lập tức bị gán cứng là `"Đang thu âm"`, trong khi trình duyệt vẫn đang treo popup xin cấp quyền Microphone (`navigator.mediaDevices.getUserMedia`).
    2. Nếu người dùng bấm từ chối (Deny/Block), khối lệnh `catch (e) {}` nuốt chửng ngoại lệ, sau đó `animateBars()` và `setInterval` VẪN TIẾP TỤC CHẠY và bộ đếm giây vẫn đếm như thật dù không có quyền mic.
    3. Hoàn toàn không hiển thị modal hướng dẫn cấp lại quyền microphone khi bị từ chối.

---

### Bug 14: /wokwi nhãn mạch bị cắt/chồng (DHT11), trang hiện "Chưa có dữ liệu"
- **Tệp nguồn:** [`simulator/static/wokwi.html`](file:///C:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/static/wokwi.html#L58-L176) và [`simulator/static/js/wokwi.js`](file:///C:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/static/js/wokwi.js#L80-L90,L503-L534)
  - Tại dòng 58 của `simulator/static/wokwi.html`:
    ```html
    <div class="card-head">
      <h2>Mạch mô phỏng</h2>
      <span id="hoverHoleInfo">Chưa có dữ liệu</span>
    </div>
    ```
  - Tại dòng 84 của `simulator/static/js/wokwi.js`:
    Phần tử `#hoverHoleInfo` chỉ được gán nội dung khi người dùng hover chuột vào một lỗ cắm cụ thể trên Breadboard:
    `document.getElementById('hoverHoleInfo').textContent = 'Đang trỏ vào: [${id.toUpperCase()}] — ${desc}';`
    Ngoài ra trong toàn bộ mã nguồn không có bất kỳ dòng nào khác cập nhật `#hoverHoleInfo`. Do đó, khi mới tải trang hoặc khi người dùng không hover chuột, trang luôn hiển thị dòng chữ thiếu thẩm mỹ: `"Chưa có dữ liệu"` dù mô phỏng phần cứng đang chạy bình thường.
  - Về lỗi nhãn mạch bị cắt/chồng lấn:
    Tại dòng 163–175 của `simulator/static/wokwi.html`:
    ```html
    <div class="comp-tag" style="left: 350px; top: 360px; font-size:10px; border-color:#c084fc;">Mắt thu VS1838B (Chân D5)</div>
    ...
    <div class="comp-tag" style="left: 500px; top: 360px; font-size:10px; border-color:#38bdf8;">Cảm biến DHT11 (Chân D6)</div>
    ...
    <div class="comp-tag" style="left: 632px; top: 360px; font-size:10px; border-color:#f43f5e;">Còi Buzzer 5V (Chân D8)</div>
    ```
    Quan sát hình học:
    - Cả 3 thẻ nhãn đều dùng chung tọa độ dọc `top: 360px` với thuộc tính CSS `.comp-tag` có nền đục `background: rgba(15, 23, 42, 0.92)`.
    - Thẻ nhãn DHT11 bắt đầu tại `left: 500px`. Chuỗi ký tự `"Cảm biến DHT11 (Chân D6)"` (25 ký tự font 10px kèm padding 14px + border) có bề ngang ~161px $\rightarrow$ kéo dài tới vị trí `661px`.
    - Tuy nhiên thẻ nhãn Còi Buzzer lại bắt đầu ở tọa độ `left: 632px` ($632 < 661$).
    - Kết quả: Thẻ nhãn Buzzer đè trực tiếp lên 29px phần đuôi của thẻ nhãn DHT11, che khuất chữ `"6)"` và cắt cụt chữ `"D"`, làm nhãn DHT11 hiển thị trên màn hình bị cụt thành `"Cảm biến DHT11 (Chân D…"`.

---

## 2. Logic Chain (Chuỗi suy luận từ quan sát tới giải pháp)

### Chuỗi suy luận Bug 3:
1. Vercel Serverless không giữ kết nối TCP/WebSocket đường dài $\rightarrow$ `wss://.../ws` bị đóng sau khi bắt tay.
2. `ws.onclose` kích hoạt fallback HTTP polling `/api/state` mỗi 4 giây.
3. Khi HTTP polling thành công, hệ thống đang kết nối và đồng bộ dữ liệu bình thường qua HTTP REST $\rightarrow$ Hiển thị banner màu cam cảnh báo "Mất kết nối thời gian thực" là sai sự thật và gây hoang mang, đặc biệt khi header vẫn đề "Đã kết nối".
4. **Giải pháp:**
   - Trong `ws.onclose`: Gọi `fetch("/api/state")`. Nếu thành công $\rightarrow$ `updateConnectionUI(true)`, `applySnapshot(snap)` và ẩn banner (`hideWsReconnectBanner()`).
   - Trong `pollRestStateFallback()`: Nếu fetch thành công $\rightarrow$ ẩn banner. Chỉ khi cả WebSocket VÀ HTTP Polling đều thất bại (mất mạng thật sự) thì mới gọi `showWsReconnectBanner(...)` và `updateConnectionUI(false)`.
   - Bổ sung tệp `simulator/static/favicon.ico` hợp lệ và khai báo route tĩnh trong `vercel.json` trước dòng catch-all 404 $\rightarrow$ Triệt tiêu hoàn toàn lỗi 404 console trên production.

### Chuỗi suy luận Bug 10:
1. Khi ấn công tắc đèn, mã hiện tại chờ phản hồi mạng từ serverless mới cập nhật DOM $\rightarrow$ Gây cảm giác đơ, phản hồi chậm.
2. Khi server snapshot trả về, `renderDevices` dùng `devicesGrid.innerHTML = ""` làm nhấp nháy/mất nhãn tạm thời.
3. Nhãn phụ đề `"Phòng khách · Đang bật"` quá dài so với độ rộng cột $\rightarrow$ Bị ngắt dòng và cắt chữ diacritics tiếng Việt thành `"Đã bột"`.
4. **Giải pháp:**
   - Áp dụng Optimistic UI: Khi người dùng bấm toggle, ngay lập tức đổi trạng thái checkbox, cập nhật icon sáng/tối, đổi nhãn phụ đề thành chữ đầy đủ `"Đã bật"` / `"Đã tắt"` mà không làm rỗng nhãn, đồng thời cập nhật tức thì bộ đếm tổng thiết bị đang bật.
   - Cập nhật trực tiếp trên các phần tử DOM hiện có thay vì `innerHTML = ""`.
   - Nếu API thất bại hoặc bị RBAC từ chối $\rightarrow$ rollback trạng thái lạc quan về trạng thái trước đó.

### Chuỗi suy luận Bug 11:
1. Bản chất của `navigator.mediaDevices.getUserMedia` là bất đồng bộ và cần người dùng tương tác cho phép trên popup của hệ điều hành/trình duyệt.
2. Đặt tiêu đề `"Đang thu âm"` trước khi có quyền là sai trạng thái thực tế; chạy timer và waveform khi quyền bị từ chối là dữ liệu giả (fake telemetry).
3. **Giải pháp:**
   - Khi mở Bottom Sheet: Đặt trạng thái ban đầu là `"Đang chờ quyền mic"`.
   - Giữ nguyên bộ đếm 00:00 và thanh âm lượng đứng yên.
   - Khi `getUserMedia` thành công $\rightarrow$ Chuyển tiêu đề sang `"Đang thu âm"`, kích hoạt timer và hiệu ứng sóng âm `animateBars()`.
   - Khi `getUserMedia` bị từ chối hoặc lỗi $\rightarrow$ Đóng Bottom Sheet và mở Hộp thoại quyền Microphone (`#mobileMicPermissionModal`) hướng dẫn bật mic trong cài đặt.

### Chuỗi suy luận Bug 14:
1. Dòng `"Chưa có dữ liệu"` xuất hiện do giá trị mặc định của `#hoverHoleInfo` trong HTML không được đồng bộ với telemetry của mô phỏng khi người dùng không rê chuột.
2. Nhãn `"Cảm biến DHT11 (Chân D6)"` bị cắt do thẻ nhãn Buzzer kế bên (`left: 632px`) đè lên vùng tọa độ của nó (`500px + 161px = 661px`).
3. **Giải pháp:**
   - Điều chỉnh layout tọa độ các thẻ nhãn trên mạch: Đặt nhãn DHT11 so le hoặc lùi khoảng cách (ví dụ `top: 376px` hoặc phân bổ `left: 470px` và `left: 655px`) $\rightarrow$ Triệt tiêu 100% chồng lấn.
   - Thay thế `"Chưa có dữ liệu"` bằng dòng trạng thái telemetry mô phỏng sống động (nhiệt độ DHT11, độ ẩm đất LM393, trạng thái thiết bị) cả trong HTML khởi tạo lẫn khi `syncWokwiComponents()` chạy. Khi chuột rời khỏi chân mạch, khôi phục lại telemetry thay vì để trống.

---

## 3. Caveats (Giới hạn và Giả định)

1. **Vercel Serverless WebSocket:** Vercel hoàn toàn không hỗ trợ giao thức WebSocket nhị phân hai chiều. Do đó, cơ chế fallback sang HTTP Polling là giải pháp chính thống, đúng chuẩn kiến trúc Serverless. Cần đảm bảo tần số polling (3–4s) không làm quá tải quota Vercel Functions.
2. **Khả năng tương thích DOM IDs & Window Hooks:** Toàn bộ 68 DOM IDs và 25 `window.*` hooks trên mobile app, cùng các hook trên desktop app phải được giữ nguyên vẹn 100% để không làm gãy các bài test Challenger và E2E hiện có.
3. **Mã hóa ký tự:** Toàn bộ tệp mã nguồn và markup sửa đổi phải tuân thủ chuẩn UTF-8 LF (0 CRLF), không có BOM.

---

## 4. Conclusion (Kết luận & Định hướng thực thi)

1. **Bug 3:**
   - Trong `app.js` và `mobile_app.js`: Đồng bộ logic giữa WebSocket và Polling Fallback. Chỉ hiện banner khi polling cũng lỗi; khi polling hoạt động bình thường thì ẩn banner và đồng bộ badge header.
   - Tạo tệp `simulator/static/favicon.ico` và bổ sung route `/favicon.ico` trong `vercel.json` để xóa triệt để lỗi console 404.
2. **Bug 10:**
   - Cung cấp Optimistic UI tức thì trên cả Desktop và Mobile PWA khi bấm nút điều khiển.
   - Không dùng `innerHTML = ""` để tránh làm trống nhãn; hiển thị nhãn phụ đề đầy đủ không cắt xén (`"Đã bật"` / `"Đã tắt"`).
3. **Bug 11:**
   - Bổ sung trạng thái `"Đang chờ quyền mic"` trong Bottom Sheet ghi âm mobile.
   - Chỉ kích hoạt timer/waveform sau khi `getUserMedia` được cấp phép.
   - Tích hợp Modal Quyền Micro trên Mobile PWA khi người dùng từ chối quyền.
4. **Bug 14:**
   - Sắp xếp lại tọa độ các thẻ nhãn `.comp-tag` trên Breadboard của `/wokwi` để loại bỏ hoàn toàn hiện tượng chồng đè.
   - Xóa bỏ chuỗi `"Chưa có dữ liệu"`, hiển thị dữ liệu mô phỏng cảm biến trực quan theo thời gian thực.

---

## 5. Verification Method (Chiến lược Kiểm thử TDD)

### Kịch bản kiểm thử TDD chi tiết cho từng lỗi:

#### 1. Kiểm thử Bug 3 (WebSocket Fallback & Consistent Banner + Parity 404)
- **Tệp test đề xuất:** `tests/test_p4_bug3_ws_fallback_and_banner.py`
- **Cách viết:**
  - Viết test Playwright/Node VM giả lập sự kiện `ws.onclose`. Mock phản hồi `/api/state` trả về 200 OK snapshot.
  - **Fail trước khi vá:** `#wsReconnectBanner` không có class `hidden` (vẫn hiện cảnh báo màu vàng dù polling thành công), gây mâu thuẫn với header `#connText` ("Đã kết nối").
  - **Pass sau khi vá:** Khi polling thành công, `#wsReconnectBanner` tự động thêm class `hidden`, banner và header hoàn toàn đồng nhất.
  - Test kiểm tra `vercel.json` có route `/favicon.ico` và tệp `simulator/static/favicon.ico` tồn tại thực tế trên đĩa với mã trạng thái HTTP 200.

#### 2. Kiểm thử Bug 10 (Optimistic UI & No Label Truncation)
- **Tệp test đề xuất:** `tests/test_p4_bug10_optimistic_device_toggle.py`
- **Cách viết:**
  - Viết test kiểm tra hàm `toggleDeviceById('living_room_light')`.
  - **Fail trước khi vá:** Ngay sau khi gọi hàm (trước khi promise fetch giải quyết), switch checkbox và nhãn phụ đề không đổi trạng thái; kiểm tra việc gán `innerHTML = ""` làm rỗng `#deviceGrid`.
  - **Pass sau khi vá:** Ngay lập tức checkbox `.switch input` đổi trạng thái `checked`, phụ đề cập nhật thành `"Đã bật"`, nhãn thiết bị không bao giờ bị rỗng (`dev.name != ""`), và khi mock server lỗi thì trạng thái được rollback an toàn.

#### 3. Kiểm thử Bug 11 (Mic Permission Flow & Denied Modal)
- **Tệp test đề xuất:** `tests/test_p4_bug11_mobile_mic_permission_flow.py`
- **Cách viết:**
  - Mock `navigator.mediaDevices.getUserMedia` với Promise chưa giải quyết (pending).
  - Gọi `openVoiceBottomSheet()`.
  - **Fail trước khi vá:** Tiêu đề `#mobileVoiceSheetTitle` hiện `"Đang thu âm"`, timer và waveform chạy dù chưa có quyền mic.
  - **Pass sau khi vá:** Tiêu đề hiện `"Đang chờ quyền mic"`, timer đứng ở `00:00`. Khi promise resolve $\rightarrow$ chuyển sang `"Đang thu âm"` và bắt đầu đếm. Khi promise reject với `NotAllowedError` $\rightarrow$ sheet đóng và modal quyền mic hiển thị.

#### 4. Kiểm thử Bug 14 (Wokwi Label Layout & Telemetry Display)
- **Tệp test đề xuất:** `tests/test_p4_bug14_wokwi_label_layout_and_telemetry.py`
- **Cách viết:**
  - Phân tích cú pháp DOM `simulator/static/wokwi.html`.
  - **Fail trước khi vá:**
    1. `#hoverHoleInfo` chứa chuỗi `"Chưa có dữ liệu"`.
    2. Tọa độ của thẻ nhãn DHT11 và Buzzer cùng có `top: 360px` và khoảng cách $left_{buzzer} - left_{dht} = 132px < 155px$ (bị đè lên nhau).
  - **Pass sau khi vá:**
    1. `#hoverHoleInfo` hiển thị dữ liệu telemetry mô phỏng (chứa `"28.5°C"` hoặc `"65%"` hoặc `"Độ ẩm đất"`), không còn chuỗi `"Chưa có dữ liệu"`.
    2. Khoảng cách giữa các thẻ nhãn đảm bảo không chồng lấn hình học ($left_{buzzer} - left_{dht} \ge width_{dht}$ hoặc khác dòng `top`).

### Lệnh chạy kiểm thử chuẩn:
```powershell
python -X utf8 -m pytest tests/test_p4_bug*.py --basetemp=.pytest_tmp
```
Sau khi chạy xong tự động dọn dẹp thư mục tạm `.pytest_tmp`.
