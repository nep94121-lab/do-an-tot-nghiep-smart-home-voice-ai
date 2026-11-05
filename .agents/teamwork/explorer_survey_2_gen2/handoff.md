# BÁO CÁO KHẢO SÁT CHUYÊN SÂU YÊU CẦU R2 (MOBILE RESPONSIVE & 3D CHIPS OVERLAY)

**Người thực hiện**: `teamwork_spec_miner` / `explorer_survey_2_gen2`
**Nhiệm vụ**: Khảo sát toàn diện mã nguồn, quy chuẩn thiết kế và bộ kiểm thử cho Yêu cầu **R2**:
- Layout co giãn Responsive trên thiết bị di động (360px – 460px).
- Thuật toán đẩy lùi va chạm (Collision Repulsion) và kẹp viền biên giới (Boundary Clamping) cho các thẻ chip 3D overlay trên route `/` kèm giảm cỡ chữ (reduced font size).
- Tái cấu trúc thanh tiêu đề `.top` thành 2 hàng phân định rõ ràng:
  - Hàng 1 (Row 1): Tiêu đề Tổng quan (`<h1>`) và trạng thái kết nối máy chủ/WebSocket.
  - Hàng 2 (Row 2): Huy hiệu tài khoản (Role Badge), thời hạn truy cập (Duration/Quota), và nút Đăng xuất (Logout).
- Cắt tỉa văn bản email bằng dấu ba chấm (Ellipsis Truncation) để triệt tiêu hoàn toàn hiện tượng tràn viền, đè chữ như ghi nhận trong ảnh thực tế `C:\Users\LENOVO\datn-wt\mobile_home_3d_overlap.jpg`.
- Tuân thủ nghiêm ngặt: 0 inline scripts và 0 thẻ `<style>` trong `simulator/static/index.html`, 100% kết thúc dòng POSIX LF (0 CRLF), bảo toàn tuyệt đối toàn bộ DOM ID phục vụ kiểm thử.

---

## 1. Observation (Quan Sát Thực Nghiệm Trực Tiếp)

### 1.1. Hiện trạng lỗi trực quan từ ảnh chụp thực tế `C:\Users\LENOVO\datn-wt\mobile_home_3d_overlap.jpg`
Qua công cụ `view_file` phân tích ảnh thực tế chụp trên thiết bị di động (độ phân giải chiều rộng ~390px trên trình duyệt di động Samsung Internet/Chrome khi truy cập bản Vercel live `smart-home-voice-a.vercel.app` route `/`):
1. **Lỗi thanh tiêu đề `.top`**:
   - Chữ `Tổng quan` ở góc trái bị co ép chiều ngang nghiêm trọng dẫn đến việc chữ bị ngắt đôi dòng thành:
     ```
     Tổng
     quan
     ```
   - Cạnh bên phải trên cùng một hàng ngang flex duy nhất nhồi nhét quá nhiều phần tử:
     `👑 Cấp 1 · Chủ nhà: nep94121@gmail.com` + `Không giới hạn` + `Đăng xuất`.
   - Chuỗi email dài `nep94121@gmail.com` không hề có cơ chế cắt tỉa `text-overflow: ellipsis`, dẫn đến chiều rộng danh nghĩa của huy hiệu tài khoản lên tới hơn 230px, chiếm trọn 70% chiều ngang màn hình 360px-390px, đè nén `<h1>Tổng quan</h1>` và ép rớt/che lấp phần trạng thái kết nối WebSocket (`#btnToggleServer`).
2. **Lỗi thẻ chip 3D Overlay (`#house3dLabels .pin-3d`)**:
   - **Va chạm chùm (Cluster Collision)**: Tại khu vực trung tâm bên trên mái nhà 3D, hàng loạt nhãn thiết bị chấp hành bị chồng lấp trực tiếp lên cùng một tọa độ 2D:
     - `Quạt trần (D6): OFF`
     - `Đèn ngủ (D7): OFF`
     - `Còi báo động (D8): OFF`
     - `Đèn khách (D2): OFF`
     - `Máy bơm vườn (D3): OFF`
     - `Cửa chính (D1): CLOSED`
     Toàn bộ các nhãn này đè chồng lên nhau thành một khối chữ rối loạn, hoàn toàn không đọc được nội dung trạng thái.
   - **Tràn viền cắt cụt (Boundary Clipping)**: Ở mép trái khung hình 3D, nhãn `Điều hòa (D2 IR): OFF` bị chiếu ra ngoài biên màn hình, bị cắt cụt mất nửa chữ bên trái thành `a (D2 IR): OFF` do thiếu kẹp biên an toàn.
   - **Cỡ chữ quá lớn trên màn hình hẹp**: Nhãn `.pin-3d` sử dụng cỡ chữ mặc định máy tính 11px với padding `4px 9px`, mỗi chip dài ~120px–140px. Với khung Three.js trên mobile chỉ rộng ~330px, 2 chip đặt ngang đã chiếm trọn chiều rộng khung nhìn.

---

### 1.2. Phân tích mã nguồn `simulator/static/index.html`
- **Vị trí thanh tiêu đề `.top`** (`simulator/static/index.html` dòng 49–81):
  ```html
  <header class="top">
    <h1>Tổng quan</h1>
    <div class="top-actions">
      <span class="status" id="homeCurrentAccountBadge" title="Tài khoản đang đăng nhập">
        👑 Chủ nhà · nep94121@gmail.com
      </span>
      <span class="status" id="homeSessionDurationBadge" title="Thời hạn truy cập còn lại" style="display:none;" hidden>
        Không giới hạn
      </span>
      <button type="button" class="btn btn-secondary" id="btnLogoutHome" style="min-height:34px; padding:0 12px; font-size:12px;">
        Đăng nhập / Đổi TK
      </button>
      <span class="status" id="btnToggleServer" role="button" tabindex="0" aria-label="Đã kết nối">
        <span class="dot" id="connDot"></span>
        <span id="connText">Đã kết nối</span>
        <span id="homeServerStatusBadge" class="transport-badge" style="margin-left:6px; font-size:11px; opacity:0.85; padding:2px 6px; border-radius:6px; background:rgba(255,255,255,0.08);">WebSocket</span>
      </span>
      <details class="menu">
        <summary>Tùy chọn <svg class="icon"><use href="#i-chevron"/></svg></summary>
        <div class="menu-panel">
          <label for="selActiveSpeaker">Vai trò thử</label>
          <select id="selActiveSpeaker">
            <option value="tuan_anh" selected>Chủ nhà · Nguyễn Tuấn Anh</option>
            <option value="thanh_vien_a">Gia đình · Thành viên A</option>
            <option value="thanh_vien_b">Gia đình · Thành viên B</option>
            <option value="khach_c">Khách · Khách C</option>
            <option value="stranger_1">Người lạ</option>
          </select>
          <button type="button" id="btnReset">Đặt lại mô phỏng</button>
        </div>
      </details>
    </div>
  </header>
  ```
  *Nhận xét*: Toàn bộ 5 phần tử (`homeCurrentAccountBadge`, `homeSessionDurationBadge`, `btnLogoutHome`, `btnToggleServer`, `menu`) đều bị nhét chung vào một thẻ `<div class="top-actions">`. Khi hiển thị, flexbox mặc định dàn trải tất cả trên cùng một dòng.
- **Vị trí khung nhìn 3D & nhãn overlay** (`simulator/static/index.html` dòng 117–124):
  ```html
  <div id="house3dViewport" class="viewport" role="img" aria-label="Vị trí mô hình 3D Toàn cảnh">
    <div id="house3dLabels" class="house3d-labels"></div>
    <span class="viewport-note">
      <span class="note-desktop">Kéo để xoay · Cuộn để phóng to</span>
      <span class="note-mobile">Kéo để xoay</span>
    </span>
  </div>
  ```
- **Thanh điều hướng di động chân trang** (`simulator/static/index.html` dòng 207–212):
  ```html
  <nav class="mobile-nav" aria-label="Điều hướng di động">
    <a class="active" href="/" aria-current="page"><svg class="icon"><use href="#i-home"/></svg>Nhà</a>
    <a href="/auth"><svg class="icon"><use href="#i-shield"/></svg>Xác thực</a>
    <a href="/wokwi"><svg class="icon"><use href="#i-cpu"/></svg>Phần cứng</a>
    <a href="/logs"><svg class="icon"><use href="#i-log"/></svg>Nhật ký</a>
  </nav>
  ```

---

### 1.3. Phân tích mã nguồn `simulator/static/css/style.css`
- **Định dạng thanh `.top` và `.top-actions` trên Desktop** (dòng 187–237):
  ```css
  .top,
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 24px;
  }
  .top-actions,
  .top-right,
  .actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .status,
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--muted);
    white-space: nowrap;
    background: transparent;
    border: 0;
    padding: 4px 2px;
    font-weight: 400;
    font-size: 13px;
  }
  ```
- **Định dạng thẻ chip `.pin-3d`** (dòng 427–447):
  ```css
  .pin-3d {
    position: absolute;
    left: 0;
    top: 0;
    pointer-events: auto;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 9px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 500;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(15, 23, 42, 0.88);
    color: #e2e8f0;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
    transition: background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease, filter 0.15s ease;
  }
  ```
- **Media Query Mobile hiện tại `@media (max-width: 700px)`** (dòng 946–974):
  ```css
  @media (max-width: 700px) {
    .app { display: block; }
    .sidebar, .side { display: none; }
    .content, .main { padding: 20px 16px 88px; }
    .top, .topbar {
      align-items: flex-start;
      margin-bottom: 18px;
    }
    h1, .top h1, .title h2 { font-size: 22px; }
    .top-actions, .top-right { gap: 8px; }
    .status { font-size: 11px; }
    .viewport, .house3d-viewport { height: 220px; }
  }
  ```
  *Điểm thiếu sót lớn*:
  - Chưa hề có quy tắc chia 2 hàng cho `.top`.
  - Chưa hề có quy tắc `max-width` kèm `overflow: hidden; text-overflow: ellipsis;` cho `#homeCurrentAccountBadge`.
  - Chưa hề có định dạng giảm cỡ chữ / padding cho `.pin-3d` trên mobile.
  - Chưa hề có media query chuyên biệt cho dải màn hình `360px – 460px` (`@media (max-width: 480px)`).

---

### 1.4. Phân tích mã nguồn Three.js trong `simulator/static/house3d.js`
- **Danh sách neo 3D `PIN_META`** (dòng 166–179):
  ```javascript
  const PIN_META = [
    { id: "main_door", kind: "device", icon: "🚪", shortName: "Cửa chính (D1)", pos: [-2.95, 1.65, 3.95] },
    { id: "living_room_light", kind: "device", icon: "💡", shortName: "Đèn khách (D2)", pos: [-3.45, 2.35, 0.45] },
    { id: "fan", kind: "device", icon: "🌀", shortName: "Quạt trần (D6)", pos: [-0.75, 3.65, -2.15] },
    { id: "ac", kind: "device", icon: "❄️", shortName: "Điều hòa (D2 IR)", pos: [-4.15, 4.15, -3.55] },
    { id: "bedroom_light", kind: "device", icon: "🛏️", shortName: "Đèn ngủ (D7)", pos: [3.25, 3.15, -0.85] },
    { id: "alarm_siren", kind: "device", icon: "🚨", shortName: "Còi báo động (D8)", pos: [0.55, 2.95, 3.74] },
    { id: "garden_pump", kind: "device", icon: "💧", shortName: "Máy bơm vườn (D3)", pos: [3.55, 1.15, 4.35] },
    { id: "sensor_soil_a0", kind: "sensor", cam: "garden", icon: "🌱", shortName: "Độ ẩm đất (A0)", pos: [1.55, 1.25, 4.35] },
    { id: "sensor_dht11_d6", kind: "sensor", cam: "living", icon: "🌡️", shortName: "Nhiệt/Ẩm (D6)", pos: [0.1, 2.15, -1.1] },
    { id: "sensor_ir_d5", kind: "sensor", cam: "living", icon: "📡", shortName: "Thu/Phát IR (D5/D2)", pos: [-2.6, 0.92, -0.75] },
    { id: "board_esp8266", kind: "sensor", cam: "board", icon: "🔌", shortName: "Mạch Chính ESP8266", pos: [-0.25, 1.65, 2.45] },
    { id: "mic_speaker_unit", kind: "sensor", cam: "board", icon: "🎙️🔊", shortName: "Mic & Loa Mạch (RX/D4)", pos: [-0.25, 2.02, 2.45] },
  ];
  ```
- **Hàm định vị vị trí nhãn `updatePinPositions()`** (dòng 1287–1307):
  ```javascript
  function updatePinPositions() {
    if (!labelsContainer || !renderer) return;
    const w = container.clientWidth;
    const h = container.clientHeight;
    PIN_META.forEach((m) => {
      const el = pinElements[m.id];
      if (!el) return;
      const v = pinAnchors[m.id].clone().project(camera);
      const stSpan = el.querySelector(".pin-state");
      const hasValProp = el.dataset && el.dataset.hasValue !== undefined ? el.dataset.hasValue : el.getAttribute("data-has-value");
      const hasValue = hasValProp !== "false" && Boolean(stSpan && stSpan.textContent && stSpan.textContent.trim());
      if (!hasValue || v.z > 1 || (m.kind === "sensor" && camGoal.radius >= 10.0)) {
        el.style.display = "none";
        return;
      }
      el.style.display = "inline-flex";
      const x = (v.x * 0.5 + 0.5) * w;
      const y = (-(v.y * 0.5) + 0.5) * h;
      el.style.transform = `translate(-50%, -50%) translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    });
  }
  ```
  *Bản chất nguyên nhân lỗi va chạm & cắt cụt*:
  - Phép tính tọa độ 2D là một phép chiếu độc lập từng điểm: $x = (v.x \cdot 0.5 + 0.5) \cdot w$ và $y = (-v.y \cdot 0.5 + 0.5) \cdot h$.
  - **Không hề có bước kiểm tra va chạm giữa các chip (No Collision Detection/Repulsion)**: Khi góc nhìn Toàn cảnh (Overview) chiếu các thiết bị trong nhà (`fan`, `bedroom_light`, `alarm_siren`, `living_room_light`, `garden_pump`), các tọa độ chiếu $(x, y)$ rơi sát nhau trong bán kính 10–30px. Vì các chip không đẩy lùi nhau, chúng bị đè chồng 100% lên nhau.
  - **Không hề có bước kẹp viền biên giới (No Boundary Clamping)**: Với phép tịnh tiến tâm `translate(-50%, -50%)`, nếu tọa độ chiếu $x \approx 10\text{px}$ (ví dụ Điều hòa D2 IR), chip rộng 120px sẽ có nửa bên trái nằm ở khoảng $[-50\text{px}, 0\text{px}]$. Do `.house3d-labels` có thuộc tính `overflow: hidden`, nửa bên trái của chip lập tức bị cắt đứt.

---

### 1.5. Khảo sát các ràng buộc kiểm thử tự động (Test Suite Invariants)
1. **`tests/test_challenger_m4_security.py`**:
   - `test_html_files_cleanliness_zero_inline_styles_and_scripts()`:
     - 6 tệp HTML bắt buộc **0 thẻ `<style>`** và **0 thẻ `<script>` không có thuộc tính `src=`**.
     - Đã xác minh thực tế qua lệnh Python: `style tags: 0`, `inline scripts: []` -> ĐẠT 100%.
2. **`tests/test_phase5_r4_house3d_overlay.py`**:
   - Khảo sát mã tĩnh yêu cầu:
     - `buildFloatingPins()` phải có: `el.dataset.hasValue = "false";`, `el.style.display = "none";`, `<strong class="pin-state"></strong>`.
     - `updateDevices()` phải có: `stateVal`, `pin.dataset.hasValue = "false"`, `pin.dataset.hasValue = "true"`.
     - `updatePinPositions()` phải giữ nguyên các chuỗi kiểm tra `hasValue` và `stSpan`.
   - Kết quả chạy kiểm thử độc lập: `9 passed in 1.68s`.
3. **`tests/test_challenger_m3_stress_dom_raycaster.py`**:
   - Yêu cầu cấu trúc:
     - `.house3d-labels { pointer-events: none; }`
     - `.pin-3d { pointer-events: auto; }`
     - `.pin-3d .pin-icon { display: inline-flex; }`
     - `#lblCurrentCameraView`, `div.camera-toolbar` với đúng 7 nút `btn-cam`
     - `#house3dViewport` chứa `#house3dLabels` và `.viewport-note`
     - Gọi `SmartHome3D.init('house3dViewport', 'house3dLabels', toggleDeviceById)`
   - Kết quả chạy kiểm thử độc lập: `20 passed in 1.38s`.
4. **`tests/test_playwright_3roles_live.py` & `tests/test_adversarial_m1_challenger.py`**:
   - Yêu cầu bắt buộc các DOM ID sau phải tồn tại và hoạt động chính xác:
     `#homeCurrentAccountBadge`, `#homeSessionDurationBadge`, `#btnLogoutHome`, `#btnToggleServer`, `#connDot`, `#connText`, `#homeServerStatusBadge`, `#homeLoginGateModal`.
   - Kết quả chạy kiểm thử: `8 passed in 18.39s` và `5 passed in 21.96s`.
5. **Kiểm tra kết thúc dòng (CRLF Check)**:
   - Toàn bộ thư mục `simulator/static/` không chứa bất kỳ byte `\r\n` nào (100% POSIX LF).

---

## 2. Logic Chain (Chuỗi Lập Luận Từ Quan Sát Đến Giải Pháp)

```
[Quan sát 1: Ảnh mobile_home_3d_overlap.jpg]
  ├── Tiêu đề "Tổng quan" bị bẻ gãy 2 dòng "Tổng" / "quan"
  ├── Huy hiệu nep94121@gmail.com + Không giới hạn + Đăng xuất dồn trên 1 dòng
  └── Các thẻ chip 3D overlay đè chồng nhau và bị cắt cụt mép trái
         │
         ▼
[Nguyên nhân gốc rễ (Root Causes)]
  ├── 1. simulator/static/index.html & style.css:
  │      - .top chỉ có 1 hàng flex duy nhất, không có cấu trúc phân chia 2 hàng.
  │      - #homeCurrentAccountBadge thiếu max-width và text-overflow: ellipsis.
  ├── 2. simulator/static/house3d.js:
  │      - updatePinPositions() chỉ dùng phép chiếu 3D thuần túy, không có vòng lặp đẩy lùi va chạm.
  │      - Không có thuật toán kẹp viền biên [pad + halfW, w - pad - halfW].
  │      - .pin-3d dùng chung font 11px trên màn hình mobile 360px.
  └── 3. Ràng buộc bảo toàn:
         - Không được vi phạm regex trong test_challenger_m4_security (0 inline script/style).
         - Không được vi phạm test_phase5_r4_house3d_overlay (hasValue, stSpan, stateVal).
         - Giữ nguyên 100% DOM IDs phục vụ Playwright và Pytest.
         │
         ▼
[Giải pháp kiến trúc R2 đề xuất]
  ├── Bước 1: Tái cấu trúc .top thành 2 hàng độc lập trong index.html & style.css
  │      - Hàng 1 (top-row-main): <h1>Tổng quan</h1> + #btnToggleServer + <details class="menu">
  │      - Hàng 2 (top-row-account): #homeCurrentAccountBadge + #homeSessionDurationBadge + #btnLogoutHome
  │      - CSS: #homeCurrentAccountBadge { flex: 1 1 auto; min-width: 0; max-width: 170px; text-overflow: ellipsis; }
  ├── Bước 2: Bổ sung Thuật toán Đẩy lùi va chạm (Collision Repulsion) & Kẹp viền (Clamping) vào house3d.js
  │      - Giữ nguyên toàn bộ guards hasValue / stSpan để vượt qua test_phase5_r4.
  │      - Thu thập tọa độ chiếu 2D của các chip đang hiển thị.
  │      - Chạy vòng lặp đẩy lùi va chạm (3 chu kỳ relaxation) tách trục Y/X.
  │      - Kẹp biên an toàn: x trong [pad + halfW, w - pad - halfW], y trong [pad + halfH, h - pad - halfH].
  └── Bước 3: Định dạng Responsive CSS cho mobile 360px – 460px
         - Giảm cỡ chữ .pin-3d xuống 10px, padding 2.5px 7px, gap 3px.
         - Tinh chỉnh khoảng cách lề trên mobile để không còn hiện tượng đè chồng.
```

---

## 3. Bảng Khảo Sát Đặc Tả & Tính Năng (Features Discovered)

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Header | Cấu trúc 2 hàng di động | Tách header `.top` thành Hàng 1 (Tiêu đề + Kết nối) và Hàng 2 (Tài khoản + Quota + Đăng xuất) | DOM nodes, Viewport width (360–460px) | 2 flex-rows riêng biệt, không đè nén | Flex wrap tự nhiên nếu màn hình siêu hẹp (<320px) | `index.html:49`, `style.css:187,958` |
| 2 | Header | Truncate Email Ellipsis | Cắt ngắn chuỗi email dài trên `#homeCurrentAccountBadge` bằng dấu `...` | Chuỗi email (vd: `nep94121@gmail.com`) | `👑 Cấp 1 · Chủ nhà: nep94121...` | Giữ nguyên full email trong thuộc tính `title` | `app.js:1565`, `style.css:225` |
| 3 | 3D Overlay | Kẹp viền Boundary Clamping | Đảm bảo tâm và mép của thẻ `.pin-3d` không bao giờ vượt ra ngoài khung Three.js | Tọa độ chiếu 2D `(x, y)`, kích thước container `(w, h)` | `x` và `y` được clamp trong khoảng an toàn `[pad+hw, w-pad-hw]` | Không bị cắt cụt mép chữ như trường hợp Điều hòa D2 IR | `house3d.js:1287`, `style.css:420` |
| 4 | 3D Overlay | Đẩy lùi va chạm Collision Repulsion | Thuật toán relaxation đẩy các chip trùng tọa độ dãn cách theo trục Y/X | Danh sách các chip đang hiển thị kèm `(x, y, w, h)` | Tọa độ dãn cách không đè chữ | Nếu quá nhiều chip cùng hội tụ, tự động xếp tầng lệch nhau | `house3d.js:1294`, `style.css:427` |
| 5 | 3D Overlay | Reduced Font Size Mobile | Giảm kích thước chip trên mobile (10px, padding 2.5px 7px) | Viewport width $\le 700\text{px}$ / $\le 480\text{px}$ | Kích thước chip thu gọn 30% | Vẫn duy trì touch target và hiển thị inline-flex cho icon | `style.css:427,946` |
| 6 | Navigation | Mobile Bottom Nav | Thanh điều hướng chân trang 4 mục cố định trên di động | Route paths (`/`, `/auth`, `/wokwi`, `/logs`) | Fixed bottom nav với safe-area-inset | Ẩn trên desktop (>700px) | `index.html:207`, `style.css:1021` |
| 7 | Security | Clean HTML Invariant | Đảm bảo 0 thẻ `<style>` và 0 thẻ `<script>` inline trong file HTML | Tệp `index.html` | Passed `test_challenger_m4_security.py` | Vi phạm nếu có `<style>` hoặc script không có `src` | `test_challenger_m4_security.py:418` |

---

## 4. Bảng Tình Huống Biên & Đối Kháng (Edge Cases)

| # | Feature | Input | Observed / Expected Behavior |
|---|---------|-------|------------------------------|
| 1 | Header Ellipsis | Email người dùng siêu dài (ví dụ: `nguyentuananh.smart.home.capstone.2026@gmail.com`) | Trước: Tràn vỡ toàn bộ header, nút Đăng xuất bị đẩy rơi khỏi viewport. Sau: Cắt cụt gọn gàng thành `👑 Cấp 1 · Chủ nhà: nguyentuananh...`, nút Đăng xuất vẫn giữ nguyên vị trí góc phải. |
| 2 | Header Quota | Khách Cấp 3 có thời hạn `Hiệu lực còn 01:23:45` | Cả 3 phần tử (Huy hiệu, Thời hạn, Nút đổi tài khoản) cùng co giãn trên Hàng 2 với `gap: 6px`, không va chạm với Hàng 1. |
| 3 | 3D Boundary | Thiết bị nằm sát góc trên bên trái (`ac`: `pos: [-4.15, 4.15, -3.55]`) | Trước: Bị cắt thành `a (D2 IR): OFF`. Sau: Thuật toán boundary clamping dịch $x$ sang phải ít nhất `pad + halfW` (khoảng 45px), hiển thị trọn vẹn `❄️ Điều hòa (D2 IR): OFF`. |
| 4 | 3D Collision | 4 thiết bị cùng bật ở khu vực trung tâm (`fan`, `bedroom_light`, `alarm_siren`, `living_room_light`) | Trước: Đè chồng 100% tại tọa độ $(\sim 160\text{px}, \sim 60\text{px})$. Sau: Vòng lặp đẩy lùi va chạm tách chúng theo 2 hàng dọc so le, mỗi chip cách nhau tối thiểu 24px chiều cao. |
| 5 | 3D Empty State | Thiết bị chưa nhận được trạng thái từ máy chủ (`stateVal = ""`) | Pin giữ nguyên `display: none` và `dataset.hasValue = "false"`, không tham gia vào vòng tính toán va chạm, tuân thủ 100% `test_phase5_r4_house3d_overlay.py`. |
| 6 | Viewport Resize | Xoay ngang màn hình điện thoại (Landscape 640px) hoặc co về 360px | Sự kiện `window.onResize` cập nhật camera aspect và renderer size, `updatePinPositions()` tự động tính lại tọa độ và kẹp viền theo kích thước thực tế mới. |
| 7 | Touch Drag vs Click | Người dùng vuốt màn hình để xoay mô hình 3D (độ lệch $> 10\text{px}$) | `isDragging = true`, không kích hoạt nhầm sự kiện bật/tắt thiết bị trên các chip (`handleRaycastClick`), vượt qua kiểm thử `test_challenger_m3_stress_dom_raycaster.py`. |

---

## 5. Caveats (Các Điểm Lưu Ý & Giới Hạn Nghiên Cứu)

1. **Ràng buộc kiểm tra tĩnh của Pytest**:
   - Tệp `tests/test_phase5_r4_house3d_overlay.py` kiểm tra tĩnh mã nguồn `house3d.js` bằng cách tìm kiếm chính xác các chuỗi:
     `assert 'el.dataset.hasValue = "false";' in code`
     `assert 'el.style.display = "none";' in code`
     `assert '<strong class="pin-state"></strong>' in code`
     `assert "stateVal" in code`
     `assert 'pin.dataset.hasValue = "false"' in code`
     `assert 'pin.dataset.hasValue = "true"' in code`
     `assert "hasValue" in code`
     `assert "stSpan" in code`
   - Khi triển khai logic đẩy lùi va chạm trong `updatePinPositions()`, **bắt buộc phải giữ nguyên toàn bộ các cấu trúc chuỗi này**.
2. **Ràng buộc kiểm tra thẻ script & style**:
   - `tests/test_challenger_m4_security.py` cấm tuyệt đối mọi thẻ `<style>` và script inline trong `simulator/static/index.html`. Toàn bộ CSS bắt buộc phải viết vào `simulator/static/css/style.css`.
3. **Bảo toàn DOM IDs**:
   - Tuyệt đối không xóa hoặc đổi tên các ID: `#homeCurrentAccountBadge`, `#homeSessionDurationBadge`, `#btnLogoutHome`, `#btnToggleServer`, `#connDot`, `#connText`, `#homeServerStatusBadge`, `#house3dViewport`, `#house3dLabels`.

---

## 6. Conclusion & Concrete Implementation Recommendations (Kết Luận & Khuyến Nghị Triển Khai)

### Khuyến nghị 1: Tái cấu trúc thanh tiêu đề `.top` trong `simulator/static/index.html`
Thay thế khối `<header class="top">` hiện tại bằng cấu trúc 2 hàng trực quan:
```html
      <header class="top">
        <div class="top-row top-row-main">
          <h1>Tổng quan</h1>
          <div class="top-status-wrap">
            <span class="status" id="btnToggleServer" role="button" tabindex="0" aria-label="Đã kết nối">
              <span class="dot" id="connDot"></span>
              <span id="connText">Đã kết nối</span>
              <span id="homeServerStatusBadge" class="transport-badge" style="margin-left:6px; font-size:11px; opacity:0.85; padding:2px 6px; border-radius:6px; background:rgba(255,255,255,0.08);">WebSocket</span>
            </span>
            <details class="menu">
              <summary>Tùy chọn <svg class="icon"><use href="#i-chevron"/></svg></summary>
              <div class="menu-panel">
                <label for="selActiveSpeaker">Vai trò thử</label>
                <select id="selActiveSpeaker">
                  <option value="tuan_anh" selected>Chủ nhà · Nguyễn Tuấn Anh</option>
                  <option value="thanh_vien_a">Gia đình · Thành viên A</option>
                  <option value="thanh_vien_b">Gia đình · Thành viên B</option>
                  <option value="khach_c">Khách · Khách C</option>
                  <option value="stranger_1">Người lạ</option>
                </select>
                <button type="button" id="btnReset">Đặt lại mô phỏng</button>
              </div>
            </details>
          </div>
        </div>
        <div class="top-row top-row-account" id="topAccountRow">
          <span class="status" id="homeCurrentAccountBadge" title="Tài khoản đang đăng nhập">
            👑 Chủ nhà · nep94121@gmail.com
          </span>
          <span class="status" id="homeSessionDurationBadge" title="Thời hạn truy cập còn lại" style="display:none;" hidden>
            Không giới hạn
          </span>
          <button type="button" class="btn btn-secondary" id="btnLogoutHome" style="min-height:30px; padding:0 10px; font-size:11px; white-space:nowrap;">
            Đăng nhập / Đổi TK
          </button>
        </div>
      </header>
```

### Khuyến nghị 2: Bổ sung định dạng CSS cho Header & 3D Chips trong `simulator/static/css/style.css`
1. Cấu trúc 2 hàng:
```css
.top {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 24px;
}
.top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.top-row-main {
  gap: 12px;
}
.top-status-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}
.top-row-account {
  gap: 8px;
  justify-content: flex-end;
}
```
2. Cắt tỉa văn bản email bằng dấu ba chấm (Ellipsis Truncation):
```css
#homeCurrentAccountBadge {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
}
```
3. Media query di động 360px – 460px (`@media (max-width: 480px)` hoặc `@media (max-width: 700px)`):
```css
@media (max-width: 700px) {
  .top {
    gap: 8px;
    margin-bottom: 16px;
  }
  .top-row-main {
    justify-content: space-between;
  }
  .top-row-account {
    justify-content: space-between;
    width: 100%;
  }
  #homeCurrentAccountBadge {
    max-width: 165px;
    font-size: 11px;
    flex: 1 1 auto;
    min-width: 0;
  }
  #homeSessionDurationBadge {
    font-size: 11px;
    flex: 0 0 auto;
  }
  #btnLogoutHome {
    font-size: 11px;
    padding: 3px 8px;
    min-height: 28px;
    flex: 0 0 auto;
  }
  .pin-3d {
    font-size: 10px;
    padding: 2.5px 7px;
    gap: 3px;
  }
  .pin-3d .pin-icon {
    font-size: 11px;
  }
  .pin-3d .pin-state,
  .pin-3d strong {
    padding: 1px 3px;
  }
}
```

### Khuyến nghị 3: Nâng cấp thuật toán trong `simulator/static/house3d.js`
Nâng cấp hàm `updatePinPositions()` với logic đẩy lùi va chạm và kẹp biên an toàn:
```javascript
  function updatePinPositions() {
    if (!labelsContainer || !renderer) return;
    const w = container.clientWidth;
    const h = container.clientHeight;
    const visiblePins = [];

    PIN_META.forEach((m) => {
      const el = pinElements[m.id];
      if (!el) return;
      const v = pinAnchors[m.id].clone().project(camera);
      const stSpan = el.querySelector(".pin-state");
      const hasValProp = el.dataset && el.dataset.hasValue !== undefined ? el.dataset.hasValue : el.getAttribute("data-has-value");
      const hasValue = hasValProp !== "false" && Boolean(stSpan && stSpan.textContent && stSpan.textContent.trim());
      if (!hasValue || v.z > 1 || (m.kind === "sensor" && camGoal.radius >= 10.0)) {
        el.style.display = "none";
        return;
      }
      el.style.display = "inline-flex";

      let rawX = (v.x * 0.5 + 0.5) * w;
      let rawY = (-(v.y * 0.5) + 0.5) * h;

      const isMobile = w < 500;
      const chipW = el.offsetWidth || (isMobile ? 86 : 110);
      const chipH = el.offsetHeight || (isMobile ? 22 : 26);
      const halfW = chipW * 0.5;
      const halfH = chipH * 0.5;

      // 1. Kẹp biên an toàn ban đầu
      const pad = 6;
      rawX = Math.max(pad + halfW, Math.min(w - pad - halfW, rawX));
      rawY = Math.max(pad + halfH, Math.min(h - pad - halfH, rawY));

      visiblePins.push({
        el,
        x: rawX,
        y: rawY,
        hw: halfW,
        hh: halfH,
      });
    });

    // 2. Thuật toán đẩy lùi va chạm giữa các chip hiển thị (3 chu kỳ relaxation)
    const iterations = 3;
    const gapX = 6;
    const gapY = 4;
    for (let iter = 0; iter < iterations; iter++) {
      for (let i = 0; i < visiblePins.length; i++) {
        for (let j = i + 1; j < visiblePins.length; j++) {
          const p1 = visiblePins[i];
          const p2 = visiblePins[j];
          const dx = p2.x - p1.x;
          const dy = p2.y - p1.y;
          const minDistX = p1.hw + p2.hw + gapX;
          const minDistY = p1.hh + p2.hh + gapY;
          const overlapX = minDistX - Math.abs(dx);
          const overlapY = minDistY - Math.abs(dy);

          if (overlapX > 0 && overlapY > 0) {
            // Tách theo trục có độ chồng lấp nhỏ hơn để giảm biến dạng thị giác
            if (overlapY < overlapX) {
              const pushY = overlapY * 0.5;
              if (dy >= 0) {
                p2.y += pushY;
                p1.y -= pushY;
              } else {
                p2.y -= pushY;
                p1.y += pushY;
              }
            } else {
              const pushX = overlapX * 0.5;
              if (dx >= 0) {
                p2.x += pushX;
                p1.x -= pushX;
              } else {
                p2.x -= pushX;
                p1.x += pushX;
              }
            }
          }
        }
      }

      // Kẹp biên lại sau mỗi chu kỳ đẩy lùi
      const pad = 6;
      visiblePins.forEach((p) => {
        p.x = Math.max(pad + p.hw, Math.min(w - pad - p.hw, p.x));
        p.y = Math.max(pad + p.hh, Math.min(h - pad - p.hh, p.y));
      });
    }

    // 3. Cập nhật vị trí transform cuối cùng
    visiblePins.forEach((p) => {
      p.el.style.transform = `translate(-50%, -50%) translate(${Math.round(p.x)}px, ${Math.round(p.y)}px)`;
    });
  }
```

---

## 7. Verification Method (Phương Pháp Kiểm Chứng Độc Lập)

1. **Kiểm tra độ sạch mã nguồn (Cleanliness & Security)**:
   ```bash
   python -c "from tests.test_challenger_m4_security import TestStaticResourceServingAndContentTypes; t = TestStaticResourceServingAndContentTypes(); t.test_html_files_cleanliness_zero_inline_styles_and_scripts(); print('ZERO INLINE STYLES/SCRIPTS: PASS')"
   ```
2. **Kiểm tra chuẩn kết thúc dòng (0 CRLF)**:
   ```bash
   python -c "import pathlib; crlf = [p for p in pathlib.Path('simulator/static').rglob('*') if p.is_file() and b'\r\n' in p.read_bytes()]; assert len(crlf) == 0, f'Found CRLF: {crlf}'; print('0 CRLF: PASS')"
   ```
3. **Kiểm thử hồi quy 3D Overlay & Raycaster**:
   ```bash
   python -c "import pytest; pytest.main(['-q', 'tests/test_phase5_r4_house3d_overlay.py'])"
   python -c "import pytest; pytest.main(['-q', 'tests/test_challenger_m3_stress_dom_raycaster.py'])"
   ```
4. **Kiểm thử giao diện & Bố cục DOM**:
   ```bash
   python -c "import pytest; pytest.main(['-q', 'tests/test_p4_survey3_ui_layout.py'])"
   python -c "import pytest; pytest.main(['-q', 'tests/test_adversarial_m1_challenger.py'])"
   python -c "import pytest; pytest.main(['-q', 'tests/test_challenger_m1_2_adversarial.py'])"
   ```
5. **Kiểm tra trực quan Playwright trên Viewport Mobile 360px, 390px, 430px**:
   Khởi động server trên port 8088, mở Chromium headless ở kích thước `width=360, height=800` và `width=390, height=844`, chụp ảnh màn hình lưu vào file để so sánh triệt để với `C:\Users\LENOVO\datn-wt\mobile_home_3d_overlap.jpg`:
   - Xác nhận "Tổng quan" nằm trên 1 dòng đơn.
   - Xác nhận email hiển thị dấu ba chấm không che nút Đăng xuất.
   - Xác nhận 7 chip 3D dàn đều, không đè chồng chữ lên nhau, không có chip nào bị lọt ra ngoài mép khung.
