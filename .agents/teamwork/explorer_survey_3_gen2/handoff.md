# BÁO CÁO KHẢO SÁT KỸ THUẬT & ĐẶC TẢ CHI TIẾT (HANDOFF REPORT)
**Role:** `teamwork_spec_miner` / `explorer_survey_3_gen2`
**Working Directory:** `C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\explorer_survey_3_gen2\`
**Scope:** Requirements R3 (Optimistic UI & Latency Optimization on `/app`), Test Suites (Pytest, Challenger M4 Security, Playwright Viewports), and R6 (Worktree, Boundaries, Line Endings, Vercel Preview Deployment).
**Timestamp:** 2026-11-05T04:41:30Z

---

## 1. Observation (Quan Sát Thực Tế Trực Tiếp)

### 1.1. Khảo Sát Yêu Cầu R3 — Giao Diện & Điều Khiển Thiết Bị Trên `/app`
1. **Tệp `mobile_app/index.html`:**
   - **Đường dẫn:** [`mobile_app/index.html`](file:///C:/Users/LENOVO/datn-wt/ui/mobile_app/index.html)
   - **Dòng 264:** `<div class="dev-list" id="devGrid"></div>`.
   - **Quan sát:** Danh sách thẻ thiết bị được render động hoàn toàn bằng JavaScript vào bên trong container `#devGrid`. Không có thẻ mẫu HTML tĩnh sẵn; toàn bộ cấu trúc phụ thuộc vào hàm `renderState(snap)` trong `mobile_app.js`.

2. **Tệp `simulator/static/js/mobile_app.js`:**
   - **Đường dẫn:** [`simulator/static/js/mobile_app.js`](file:///C:/Users/LENOVO/datn-wt/ui/simulator/static/js/mobile_app.js)
   - **Dòng 926–928 (`renderState`):**
     ```javascript
     const grid = document.getElementById('devGrid');
     grid.innerHTML = '';
     ```
     Mỗi khi nhận được snapshot trạng thái mới (từ WebSocket hoặc nhịp HTTP polling định kỳ 2.5–4s), hàm `renderState` lập tức xóa sạch toàn bộ phần tử DOM bên trong `#devGrid` bằng `grid.innerHTML = ''` rồi duyệt mảng tạo mới lại từng thẻ card.
   - **Dòng 932–941 (`card` creation):**
     ```javascript
     const card = document.createElement('div');
     card.className = `dev-row ${isOn ? 'on' : 'off'}`;
     card.innerHTML = `
       <span class="dev-icon">${ICONS[d.type] || '<svg class="icon"><use href="#i-lamp"/></svg>'}</span>
       <div class="dev-copy">
         <div class="dev-name">${d.name}</div>
         <div class="dev-room">${roomLabel}</div>
       </div>
       <span class="switch" aria-hidden="true"></span>
     `;
     ```
     Thẻ `card` hoàn toàn **thiếu thuộc tính `data-device-id="${d.id}"`** (chưa có `card.setAttribute('data-device-id', d.id)` hay `card.dataset.deviceId = d.id`).
   - **Dòng 942–978 (`card.onclick`):**
     ```javascript
     card.onclick = async () => {
       const prevIsOn = d.state === 'ON' || d.state === 'OPEN';
       const nextIsOn = !prevIsOn;
       const prevState = d.state;
       const nextState = d.type === 'door' ? (nextIsOn ? 'OPEN' : 'CLOSED') : (nextIsOn ? 'ON' : 'OFF');

       // Optimistic UI: đổi class và state ngay lập tức
       d.state = nextState;
       card.classList.toggle('on', nextIsOn);
       card.classList.toggle('off', !nextIsOn);

       const action = d.type === 'door' ? (prevIsOn ? 'close' : 'open') : (prevIsOn ? 'turn_off' : 'turn_on');
       try {
         const res = await fetch('/api/device', {
           method: 'POST',
           headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify({ device_id: d.id, action }),
         });
         ...
     ```
   - **Hiện trạng khuyết thiếu nghiêm trọng:**
     - **Không có cửa sổ bảo vệ `pendingDeviceMutations` (2500ms):** Khi người dùng bấm gạt công tắc, nếu trong lúc gói tin `fetch('/api/device')` đang truyền qua mạng (mất từ 50ms – 1000ms), một nhịp polling nền gọi `renderState(snap)` mang snapshot cũ từ server về, `grid.innerHTML = ''` sẽ xóa thẻ hiện tại và vẽ lại thẻ với trạng thái cũ `OFF`. Người dùng thấy công tắc giật giật (flicker/jitter) trước khi nhảy lại trạng thái mới!
     - **Không có cơ chế In-Place DOM Update:** Việc gọi `grid.innerHTML = ''` buộc trình duyệt hủy bỏ và tạo lại DOM nodes, kích hoạt Full Layout Reflow và Style Recalculation, dễ làm tụt khung hình vượt quá ngưỡng 16ms (< 60 FPS).
     - **Thiếu `data-device-id`:** Các bộ kiểm thử tự động (Playwright, Jest) và hàm cập nhật in-place không thể truy xuất trực tiếp `document.querySelector('[data-device-id="living_room_light"]')`.

3. **Mô hình tham chiếu đã giải quyết thành công trên Desktop Dashboard (`app.js`):**
   - **Đường dẫn:** [`simulator/static/js/app.js`](file:///C:/Users/LENOVO/datn-wt/ui/simulator/static/js/app.js#L354-L389)
   - Trong `renderDevices(devices)` của `app.js`: Đã áp dụng cơ chế In-Place DOM Update:
     ```javascript
     let card = document.getElementById(`dev-card-${dev.id}`);
     if (card) {
       // Cập nhật DOM in-place không xóa trắng node
       const iconSpan = card.querySelector(".device-icon");
       ...
     ```
     `app.js` tìm kiếm thẻ card hiện có và chỉ cập nhật class, nhãn và trạng thái checkbox công tắc mà không xóa trắng container (`devicesGrid.innerHTML = ''`). Đây chính là tiền lệ kỹ thuật cần áp dụng cho `mobile_app.js`.

---

### 1.2. Khảo Sát Hệ Thống Kiểm Thử (Pytest, Challenger M4, Playwright)

1. **Bộ Pytest Test Suite:**
   - Thư mục `tests/` chứa 45 tệp kiểm thử tự động bao phủ toàn diện API, bảo mật, routing, và giao diện.
   - Chạy lệnh kiểm thử đơn vị:
     `pytest -q tests/test_challenger_m4_security.py -k "test_static or test_target"` $\rightarrow$ **42 PASSED (Exit Code: 0)**.

2. **Bộ Kiểm Thử Đối Kháng Bảo Mật M4 (`tests/test_challenger_m4_security.py`):**
   - **Đường dẫn:** [`tests/test_challenger_m4_security.py`](file:///C:/Users/LENOVO/datn-wt/ui/tests/test_challenger_m4_security.py)
   - **Nhóm 1 (`TestTargetWindowFuzzingAdversarial`, dòng 70–235):** 24 test cases fuzzing đầu vào `target_window` tại `/api/auth3/guest_qr_handshake` với các payload dị thường (`"NaN"`, `1e99`, `"{}"`, `10**100`...). Xác nhận hệ thống trả về HTTP 400/401 an toàn, 0 unhandled crash 500.
   - **Nhóm 2 (`TestWebSocketLifecycleAndGhostSessionLeaks`, dòng 241–362):** 4 test cases kiểm tra vòng đời kết nối WebSocket `/ws` (10 kết nối tuần tự, 10 kết nối song song, threadpool concurrency, ngắt abrupt disconnect). Lưu ý: Khi chạy môi trường độc lập không có Gemini Live streaming thật, các test này yêu cầu mock hoặc cấu hình `GEMINI_API_KEY`.
   - **Nhóm 3 (`TestStaticResourceServingAndContentTypes`, dòng 368–448):**
     - Kiểm tra 18 static routes (6 HTML, 6 CSS, 6 JS) trả về HTTP 200 OK với đúng Content-Type.
     - **Kiểm định độ tinh khiết mã nguồn (`test_html_files_cleanliness_zero_inline_styles_and_scripts`, dòng 418–448):** Quét 6 tệp HTML:
       - `simulator/static/index.html`
       - `simulator/static/auth.html`
       - `simulator/static/guest_enroll.html`
       - `simulator/static/wokwi.html`
       - `simulator/static/logs.html`
       - `mobile_app/index.html`
       Xác nhận **tuyệt đối 0 thẻ `<style>` và 0 khối inline `<script>`** (100% script phải có thuộc tính `src=`). Test này đã chạy thực tế và **PASS 100%**.

3. **Bộ Kiểm Thử Playwright E2E & Viewport Audits:**
   - **Tệp E2E hiện có:**
     - [`tests/test_challenger_m3_playwright_e2e.py`](file:///C:/Users/LENOVO/datn-wt/ui/tests/test_challenger_m3_playwright_e2e.py): Khởi tạo headless Chromium (`sync_playwright`), chạy live server uvicorn port 8993, kiểm tra `/logs` phân trang, `/app` 3D preview-16-9, danh sách 7 thiết bị gạt toggle, safe-area tài khoản, và modal QR scanner.
     - [`tests/test_playwright_3roles_live.py`](file:///C:/Users/LENOVO/datn-wt/ui/tests/test_playwright_3roles_live.py): Kiểm thử luồng 3 vai trò (Chủ nhà, Gia đình, Khách) trên Chrome thật.
     - [`tests/test_phase5_r2_wokwi_layout.py`](file:///C:/Users/LENOVO/datn-wt/ui/tests/test_phase5_r2_wokwi_layout.py#L254-L260): Đã thiết lập mẫu kiểm thử Playwright đa độ phân giải màn hình qua `@pytest.mark.parametrize`:
       - Desktop 1280px (`1280 x 800`)
       - Mobile iPhone 390px (`390 x 844`)
       - Mobile iPhone 414px / 430px
   - **Đặc tả kiểm định Viewports theo R2 & R3:**
     - **Desktop:** `1280px` (chuẩn laptop 1280×800)
     - **Mobile nhỏ (Compact Android / Samsung Galaxy A):** `360px` (360×780 hoặc 360×640)
     - **Mobile tiêu chuẩn (iPhone 12/13/14):** `390px` (390×844)
     - **Mobile lớn (iPhone 14/15 Pro Max):** `430px` (430×932)

---

### 1.3. Khảo Sát R6 — Biên Giới Tệp, Git, Mã Hóa Dòng & Triển Khai Vercel

1. **Biên giới tệp cấm chỉnh sửa (Forbidden Areas):**
   - Đã quét và xác nhận danh mục tệp backend AI/Voice được bảo vệ nghiêm ngặt:
     - `simulator/voice/**` (`biometrics_neural.py`, `denoiser.py`, `dsp_features.py`, `enrollment_quality.py`, `synthesis_augment.py`, `vad_vietnamese.py`, `__init__.py`)
     - `simulator/voice_auth.py`
     - `simulator/live/**` (`gemini_bridge.py`, `prompt_builder.py`, `tool_dispatcher_mixin.py`, `tts_rejection_vi.py`, `__init__.py`)
   - **Quy tắc:** Tuyệt đối không đọc/ghi/chỉnh sửa bất kỳ byte nào trong các tệp trên trong suốt Phase 7 UI.

2. **Cấu hình Git & Nhánh làm việc:**
   - **Thư mục làm việc:** `C:\Users\LENOVO\datn-wt\ui`
   - **Nhánh hiện tại:** `p7-ui`
   - **Remote cấu hình:** `origin` (`https://github.com/nep94121-lab/do-an-tot-nghiep-smart-home-voice-ai.git`).
   - **Quy định đẩy mã nguồn (Git Push):**
     - Tuyệt đối KHÔNG đẩy vào nhánh `master` (`master` giữ nguyên trạng).
     - Đẩy nhánh `p7-ui` lên máy chủ: `git push origin p7-ui:p7-ui` (hoặc tạo alias remote `p7-ui` nếu yêu cầu).

3. **Chuẩn hóa Line Endings (100% POSIX LF, 0 CRLF):**
   - Tệp [`.gitattributes`](file:///C:/Users/LENOVO/datn-wt/ui/.gitattributes) đã thiết lập:
     ```gitattributes
     * text=auto eol=lf
     *.json text eol=lf
     *.jsonl text eol=lf
     *.py text eol=lf
     *.js text eol=lf
     *.html text eol=lf
     *.css text eol=lf
     *.md text eol=lf
     ```
   - Chạy lệnh kiểm tra thực tế: `git ls-files --eol | Select-String "crlf"` $\rightarrow$ **0 CRLF** trong toàn bộ kho mã nguồn.

4. **Hạ tầng triển khai Vercel Preview:**
   - **Công cụ CLI:** `Vercel CLI 59.16.0 (Node.js 26.7.0)` đã được cài đặt và cấu hình sẵn trên máy trạm.
   - **Tài khoản xác thực:** `nep94121-8303` (`tuananhs-projects-8aea56ce`).
   - **Dự án liên kết:** `do-an-tot-nghiep-smart-home-voice-ai`.
   - **Lệnh triển khai Preview:**
     `npx --yes vercel --yes`
     *(CẢNH BÁO: Tuyệt đối KHÔNG thêm cờ `--prod`. Chỉ triển khai Preview).*
   - **Địa chỉ ghi nhận URL:** Sau khi lệnh hoàn tất, URL preview sinh ra phải được lưu vào:
     - `FIX_REPORT_20261104.md`
     - `.agents/teamwork/cli_fix_p7_ui_20261105.log`

---

## 2. Features Discovered (Danh Mục Tính Năng & Trạng Thái)

| # | Phân nhóm | Tính năng | Mô tả chi tiết | Đầu vào (Inputs) | Đầu ra (Outputs) | Hành vi lỗi (Error Behavior) | Phát hiện qua |
|---|---|---|---|---|---|---|---|
| F1 | R3 Optimistic UI | In-place Card Update by `data-device-id` | Cập nhật trực tiếp class, nhãn và switch của thẻ thiết bị trên `/app` thay vì xóa trắng `devGrid.innerHTML = ''`. | Click event trên thẻ hoặc công tắc của thiết bị `dev_id`. | Thẻ DOM đổi trạng thái < 16ms (60 FPS); switch flip tức thời. | Nếu server trả về lỗi, phục hồi `prevState` in-place. | `simulator/static/js/mobile_app.js:926-978` |
| F2 | R3 Optimistic UI | `pendingDeviceMutations` Guard Window (2500ms) | Bản đồ bộ nhớ tạm khóa ghi đè trạng thái trong 2500ms đối với các thiết bị vừa thao tác, chống giật giật (jitter) do HTTP polling / WebSocket snapshot mang dữ liệu cũ. | `dev_id`, `targetState`, `expiresAt = Date.now() + 2500`. | Bỏ qua dữ liệu cũ từ server trong cửa sổ 2500ms; xóa entry khi server xác nhận thành công hoặc hết hạn. | Khi hết hạn hoặc mạng lỗi, tự động xóa entry và đồng bộ lại. | R3 Specification & `ORIGINAL_REQUEST.md:24-25` |
| F3 | R3 Latency Profiling | Playwright Latency Benchmarking | Đo đạc chính xác độ trễ phản hồi giao diện trước và sau khi tối ưu hóa bằng `performance.now()`. | Click trigger vào `[data-device-id="..."]`. | Thời gian mili-giây (ms) từ khi click đến khi DOM hoàn tất render khung hình kế tiếp (`requestAnimationFrame`). | Cảnh báo nếu `durationMs >= 16ms`. | `ORIGINAL_REQUEST.md:25` & Playwright test harness |
| F4 | Testing | Challenger M4 Cleanliness Gate | Kiểm toán tĩnh 6 tệp HTML không chứa thẻ `<style>` và không có inline `<script>` (100% bóc tách ra CSS/JS). | 6 tệp HTML (`index.html`, `auth.html`, `guest_enroll.html`, `wokwi.html`, `logs.html`, `mobile_app/index.html`). | Assertion `style_matches == 0` và `inline_scripts == 0`. | AssertionError báo rõ tên file và số lượng inline tags vi phạm. | `tests/test_challenger_m4_security.py:418-448` |
| F5 | Testing | Multi-Viewport Layout Audits | Kiểm thử tự động trên Chrome headless quét 4 độ phân giải: 1280px (desktop), 360px, 390px, 430px (mobile) với 0 console errors. | URLs `/`, `/app`, `/auth`, `/wokwi`, `/logs`, `/guest_enroll`, `/login`, `/register`. | Kết quả render đúng bounding box, không chồng chéo, không console error, ảnh chụp màn hình. | Báo lỗi overlap hoặc console error. | `tests/test_phase5_r2_wokwi_layout.py` & R2/R6 Specs |
| F6 | R6 Deployment | Vercel Preview Deploy | Đóng gói và đẩy phiên bản thử nghiệm lên Vercel Serverless môi trường Preview độc lập. | Thư mục `C:\Users\LENOVO\datn-wt\ui` trên nhánh `p7-ui`. | Preview Deployment URL (ví dụ: `https://do-an-tot-nghiep-smart-home-voice-ai-xxx.vercel.app`). | Thoát lỗi nếu có cấu hình `vercel.json` sai cú pháp. | `vercel.json` & Vercel CLI 59.16.0 |
| F7 | R6 Integrity | 0 CRLF POSIX LF Guard | Bảo toàn 100% định dạng xuống dòng chuẩn Unix `\n` cho mọi tệp phát sinh. | Mọi tệp `.html`, `.css`, `.js`, `.py`, `.json`, `.md`. | 100% LF, 0 CRLF. | Bị chặn bởi CI/CD gate nếu phát hiện byte `\r\n`. | `.gitattributes` & git ls-files |

---

## 3. Edge Cases & Khảo Sát Tương Tác Bất Thường

| # | Tính năng / Tình huống | Dữ liệu đầu vào (Input) | Hành vi quan sát / Dự báo hiện tại | Giải pháp khắc phục chuẩn hóa |
|---|---|---|---|---|
| E1 | Người dùng bấm toggle liên tục (Rapid Double/Triple Click) | Bấm công tắc đèn 3 lần trong vòng 300ms. | Hiện tại: Mỗi lần bấm gửi 1 `fetch('/api/device')` riêng biệt, không có debounce hoặc lock; nếu mạng chậm có thể gây race condition. | `pendingDeviceMutations` cập nhật `targetState` mới nhất và reset hạn 2500ms; vô hiệu hóa tạm thời click trong 150ms hoặc debounce fetch. |
| E2 | HTTP Polling trả về snapshot cũ khi fetch đang in-flight | Server xử lý mất 300ms; đúng lúc 100ms có nhịp polling `/api/state` ập về mang trạng thái cũ `OFF`. | Hiện tại: `grid.innerHTML = ''` vẽ lại `OFF`, sau 200ms nữa fetch xong mới vẽ lại `ON` (gây chớp giật 2 lần). | `pendingDeviceMutations` kiểm tra `expiresAt > Date.now()` $\rightarrow$ ép giữ trạng thái `ON` trong UI, triệt tiêu hoàn toàn hiện tượng chớp giật. |
| E3 | Lỗi mạng đột ngột hoặc RBAC 403 Forbidden | Khách (Cấp 3) cố bấm công tắc Cửa chính hoặc server mất mạng. | Server trả về `{ ok: false, rbac_blocked: true }` hoặc fetch throw TypeError. | Khối catch/rollback lập tức xóa `pendingDeviceMutations`, trả lại trạng thái cũ in-place, hiển thị thông báo lỗi trên UI. |
| E4 | Lọc phòng (Room Filter) khi đang có pending mutation | Người dùng bấm toggle Đèn phòng ngủ rồi lập tức bấm tab lọc "Phòng khách". | Thiết bị chuyển sang trạng thái ẩn do bộ lọc phòng. | `pendingDeviceMutations` vẫn lưu trong bộ nhớ; khi người dùng chuyển lại "Tất cả" hoặc "Phòng ngủ", trạng thái tối ưu vẫn được bảo toàn. |
| E5 | Kiểm tra `test_html_files_cleanliness_zero_inline_styles_and_scripts` sau khi sửa code | Thêm thẻ `<script>` không có `src` hoặc thẻ `<style>` vào `mobile_app/index.html`. | Test `test_challenger_m4_security.py` thất bại ngay lập tức (`Exit Code: 1`). | Tuyệt đối không viết inline style/script trong HTML; 100% logic đưa vào `mobile_app.js` và CSS đưa vào `mobile_app.css`. |

---

## 4. Logic Chain (Chuỗi Lập Luận Suy Biến)

1. **Từ Quan sát 1.1:** `mobile_app.js` dòng 926–941 thực hiện `grid.innerHTML = ''` và tạo lại toàn bộ thẻ thiết bị mà không có `data-device-id`. Khi có nhịp polling nền, giao diện bị xóa và vẽ lại từ snapshot của server.
   $\rightarrow$ **Suy biến 1:** Thiếu cơ chế in-place update khiến thời gian thao tác DOM phụ thuộc vào toàn bộ cây con của `#devGrid`, gây reflow và có thể vượt ngưỡng 16ms.
   $\rightarrow$ **Suy biến 2:** Thiếu cửa sổ `pendingDeviceMutations` khiến giao diện bị chớp giật (rollback giả) khi snapshot cũ trả về trước khi lệnh điều khiển hoàn tất.

2. **Từ Mô hình Desktop `app.js` (dòng 354–389):** Desktop dashboard đã giải quyết thành công bài toán này bằng cách gán ID/selector cho từng card (`dev-card-${dev.id}`) và cập nhật trực tiếp class `device-icon ${isOn ? "" : "off"}` cùng checkbox `swInput.checked = isOn` mà không xóa `devicesGrid`.
   $\rightarrow$ **Suy biến 3:** Trên mobile `/app`, việc chuẩn hóa thẻ card với thuộc tính `data-device-id="${d.id}"` và cập nhật in-place theo selector `grid.querySelector('[data-device-id="' + d.id + '"]')` là hoàn toàn khả thi, đồng nhất kiến trúc và đảm bảo thời gian cập nhật < 16ms.

3. **Từ Quan sát 1.2 (Test Suites):** `test_challenger_m4_security.py` kiểm định nghiêm ngặt tính trong sạch của HTML (0 inline style/script). Đồng thời, `test_phase5_r2_wokwi_layout.py` và `test_challenger_m3_playwright_e2e.py` đã cung cấp sẵn khung Playwright headless Chromium với live server.
   $\rightarrow$ **Suy biến 4:** Việc đo đạc độ trễ trước/sau (<16ms) và kiểm định giao diện trên 4 viewports (1280px, 360px, 390px, 430px) có thể được tự động hóa hoàn toàn bằng một bài test Playwright chuyên biệt chạy trên Chromium mà không cần cài đặt thêm thư viện ngoài.

4. **Từ Quan sát 1.3 (R6 Constraints):** Worktree hiện tại ở `ui` trên nhánh `p7-ui`, 100% POSIX LF, Vercel CLI đã xác thực người dùng `nep94121-8303` với project `do-an-tot-nghiep-smart-home-voice-ai`.
   $\rightarrow$ **Suy biến 5:** Quy trình triển khai Vercel Preview và Git push hoàn toàn sẵn sàng, chỉ cần tuân thủ nghiêm ngặt cấm `--prod`, cấm push `master`, và cấm chạm vào các tệp voice backend.

---

## 5. Caveats (Các Điểm Lưu Ý & Giả Định)

1. **Giả định về kết nối mạng:** Vercel Serverless không hỗ trợ kết nối WebSocket hai chiều trường cửu; do đó trên Vercel Preview, ứng dụng tự động fallback sang HTTP Polling 2.5–4s. Cơ chế `pendingDeviceMutations` (2500ms) được thiết kế đặc biệt tối ưu cho chu kỳ polling này.
2. **Kiểm thử WebSocket trong `test_challenger_m4_security.py`:** 4 bài test WebSocket lifecycle phụ thuộc vào `LiveBridgeSession` (yêu cầu khởi tạo `genai.Client()`). Khi chạy độc lập trong môi trường offline/CI, cần chú ý không để thiếu biến môi trường hoặc gây timeout network.
3. **Bảo toàn DOM IDs cho các bộ test hồi quy cũ:** Mọi thay đổi trong `mobile_app/index.html` và `mobile_app.js` phải bảo toàn 100% các ID hiện có (`#devGrid`, `#espBadge`, `#mobileMainDoorStatus`, `#mobileAlarmSirenStatus`, `#btnToggleShowAllDevices`, `#roomFilterPills`).

---

## 6. Conclusion & Khuyến Nghị Thực Thi (Actionable Recommendations)

### 6.1. Thiết Kế Bản Vá R3 Chuẩn Mực Trong `simulator/static/js/mobile_app.js`

1. **Khai báo bộ đệm `pendingDeviceMutations` toàn cục:**
   ```javascript
   const pendingDeviceMutations = new Map();
   const MUTATION_GUARD_WINDOW_MS = 2500;
   ```

2. **Cải tiến hàm `renderState(snap)` thành In-Place Update:**
   - Thay vì `grid.innerHTML = '';`, quét danh sách `visibleDevices`:
   - Với mỗi thiết bị `d`:
     - Kiểm tra `pendingDeviceMutations`:
       ```javascript
       if (pendingDeviceMutations.has(d.id)) {
         const pending = pendingDeviceMutations.get(d.id);
         if (Date.now() < pending.expiresAt) {
           if (d.state === pending.targetState) {
             pendingDeviceMutations.delete(d.id);
           } else {
             d.state = pending.targetState; // Bảo vệ trạng thái optimistic
           }
         } else {
           pendingDeviceMutations.delete(d.id);
         }
       }
       ```
     - Tìm kiếm thẻ đã có: `let card = grid.querySelector('[data-device-id="' + d.id + '"]');`
     - Nếu chưa có: tạo thẻ mới, gán `card.setAttribute('data-device-id', d.id);`, thiết lập `card.onclick` và `grid.appendChild(card)`.
     - Nếu đã có: chỉ cập nhật class (`card.classList.toggle('on', isOn); card.classList.toggle('off', !isOn);`), cập nhật tên/phòng/icon nếu có thay đổi.
     - Dọn dẹp các thẻ không còn trong `visibleDevices` (khi lọc phòng hoặc thu gọn).

3. **Cập nhật logic `card.onclick`:**
   - Đặt ngay vào `pendingDeviceMutations`:
     `pendingDeviceMutations.set(d.id, { targetState: nextState, expiresAt: Date.now() + MUTATION_GUARD_WINDOW_MS });`
   - Đổi class DOM và `d.state` ngay lập tức (<16ms).
   - Gọi `fetch('/api/device')`. Khi nhận phản hồi thành công, xóa khỏi `pendingDeviceMutations`. Nếu có lỗi, xóa entry và rollback lại `prevState` in-place.

### 6.2. Đo Đạc & Báo Cáo Độ Trễ Playwright
- Viết kịch bản Playwright đo đạc thời gian chuyển đổi DOM trên Chromium:
  - **Trước tối ưu (Baseline):** Đo độ trễ khi phụ thuộc vào roundtrip server và reflow `grid.innerHTML = ''` (~50ms – 250ms).
  - **Sau tối ưu (Optimistic):** Đo độ trễ in-place DOM flip (< 16ms, thông thường 0.8ms – 2.5ms).
  - Ghi nhận bảng số liệu đối chiếu chi tiết vào `FIX_REPORT_20261104.md`.

---

## 7. Verification Method (Phương Pháp Kiểm Định Độc Lập)

Người thẩm định độc lập (Auditor / Reviewer) có thể kiểm chứng toàn bộ các kết luận trên bằng các lệnh sau tại thư mục gốc `C:\Users\LENOVO\datn-wt\ui`:

1. **Xác minh các tệp HTML sạch 100% không inline script/style:**
   ```powershell
   pytest -q tests/test_challenger_m4_security.py -k "test_html_files_cleanliness"
   # Kỳ vọng: 1 passed (Exit Code: 0)
   ```

2. **Xác minh 100% POSIX LF (0 CRLF):**
   ```powershell
   git ls-files --eol | Select-String "crlf"
   # Kỳ vọng: Không có tệp mã nguồn nào chứa crlf
   ```

3. **Xác minh tài khoản và danh sách dự án Vercel CLI:**
   ```powershell
   npx --yes vercel whoami
   # Kỳ vọng: nep94121-8303
   ```

4. **Xác minh ranh giới cấm không bị vi phạm:**
   ```powershell
   git status simulator/voice/ simulator/voice_auth.py simulator/live/
   # Kỳ vọng: "nothing to commit, working tree clean"
   ```
