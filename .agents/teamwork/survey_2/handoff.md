# Báo Cáo Khảo Sát Kỹ Thuật (Phase 0 Survey) - Mảng 2
## Cổng Đăng Nhập (Login Gate), Password UX & Tương Tác Mô Hình 3D (DOM / Raycaster)

**Tác giả:** `survey_2` (Teamwork Explorer)  
**Ngày thực hiện:** 2026-11-04  
**Workspace:** `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp`  
**Tệp mục tiêu khảo sát:**
- [simulator/static/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/index.html)
- [simulator/static/js/app.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/app.js)
- [simulator/static/js/auth.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/auth.js)
- [simulator/static/house3d.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/house3d.js)
- [simulator/static/css/style.css](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/css/style.css)
- [mobile_app/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/mobile_app/index.html)
- [simulator/static/js/mobile_app.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/mobile_app.js)
- [simulator/auth_3layer.py](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/auth_3layer.py)

---

## 1. Observation (Quan sát Thực nghiệm & Bằng chứng Mã nguồn)

### 1.1. Cổng Đăng Nhập Web (`#homeLoginGateModal`) & Nút Đóng `X`
- **Tệp:** [simulator/static/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/index.html#L223-L234)
  ```html
  223: <div id="homeLoginGateModal" class="modal hidden" style="z-index:200; background:rgba(23,43,49,0.55);">
  224:   <div class="modal-content" style="max-width:460px;">
  225:     <div class="modal-header">
  226:       <div>
  227:         <h3>Đăng nhập · Nhà thông minh</h3>
  228:         <p class="subtle">Tài khoản chính Chủ nhà: nep94121@gmail.com (Mật khẩu mặc định: 123456)</p>
  229:       </div>
  230:       <button id="btnCloseLoginGateModal" type="button" class="btn-close" aria-label="Đóng">
  231:         <svg class="icon"><use href="#i-x"/></svg>
  232:       </button>
  233:     </div>
  ```
- **Tệp:** [simulator/static/js/app.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/app.js#L1245-L1251)
  ```javascript
  1245: function closeLoginGateModal() {
  1246:   if (homeLoginGateModal) homeLoginGateModal.classList.add("hidden");
  1247: }
  1248: 
  1249: if (btnCloseLoginGateModal) {
  1250:   btnCloseLoginGateModal.addEventListener("click", closeLoginGateModal);
  1251: }
  ```
- **Hiện tượng:** Nút `#btnCloseLoginGateModal` hiển thị công khai ngay trong modal header. Khi người dùng chưa đăng nhập, nếu bấm nút này, modal bị ẩn đi (`classList.add("hidden")`), người dùng có thể xem và tương tác với toàn bộ giao diện Web mà không cần xác thực tài khoản.
- **Tệp:** [simulator/static/js/app.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/app.js#L1438-L1446)
  ```javascript
  1438: try {
  1439:   const savedRaw = window.localStorage ? window.localStorage.getItem("smarthome_auth_session") : null;
  1440:   const forceLoginModal = window.location && window.location.search && window.location.search.includes("login=1");
  1441:   if (savedRaw && !forceLoginModal) {
  1442:     applyLoggedInUserBanner(JSON.parse(savedRaw));
  1443:   } else if (forceLoginModal || (typeof navigator !== "undefined" && navigator.webdriver === false && window.localStorage)) {
  1444:     openLoginGateModal();
  1445:   }
  1446: } catch (_) {}
  ```
- **Hiện tượng:** Điều kiện mở Login Gate dựa vào `navigator.webdriver === false`. Trong môi trường tự động hóa hoặc trình duyệt không gán rõ `navigator.webdriver === false` (ví dụ `undefined`), `openLoginGateModal()` không được kích hoạt, dẫn đến lọt qua cổng.

### 1.2. Các Ô Nhập Bị `readOnly = true` trong `auth.js`
- **Tệp:** [simulator/static/js/auth.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/auth.js#L52-L63)
  ```javascript
  52: if (selectedEnrollTier === 1) {
  53:   selectedSpeakerName = 'Nguyễn Tuấn Anh';
  54:   if (nameInput) {
  55:     nameInput.value = 'Nguyễn Tuấn Anh';
  56:     nameInput.readOnly = true;
  57:   }
  58:   if (emailInput) {
  59:     emailInput.value = 'nep94121@gmail.com';
  60:     emailInput.readOnly = true;
  61:   }
  62:   if (accSelect) accSelect.value = 'nep94121@gmail.com';
  63: }
  ```
- **Hiện tượng:** Khi người dùng chọn Cấp 1 (Chủ nhà), cả `nameInput` và `emailInput` bị gán cứng `readOnly = true`. Người dùng không thể click vào để sửa họ tên hay email của mình.

### 1.3. Thẻ `<form>`, Nút 👁️ Hiện/Ẩn Mật Khẩu, và Bắt Buộc 2 Ô Xác Nhận Mật Khẩu
- **Tệp:** [simulator/static/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/index.html#L242-L310)
  - Tab 1: `<div id="gatePanelLogin" style="display:grid; gap:10px;">` (dòng 242) là `<div>`, không phải `<form>`. Người dùng gõ mật khẩu và bấm Enter không có tác dụng, bắt buộc phải dùng chuột bấm nút `#btnSubmitGateLogin`.
  - Tab 2: `<div id="gatePanelRegister"...>` (dòng 257) là `<div>`. Đã có 2 ô: `gateRegPassword` và `gateRegConfirmPassword`.
  - Tab 3: `<div id="gatePanelForgot"...>` (dòng 288) là `<div>`. Đã có 2 ô: `gateForgotNewPassword` và `gateForgotConfirmPassword`.
  - Toàn bộ các ô nhập mật khẩu trên Web (`gateLoginPassword`, `gateRegPassword`, `gateRegConfirmPassword`, `gateForgotNewPassword`, `gateForgotConfirmPassword`) đều không có nút 👁️ toggle type password/text.
- **Tệp:** [mobile_app/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/mobile_app/index.html#L22-L33)
  ```html
  22: <form id="mobileLoginForm" class="login-form" onsubmit="submitMobileLogin(event)">
  23:   <div>
  24:     <label class="muted" for="mobileLoginEmail" style="display:block;margin-bottom:4px;">Email</label>
  25:     <input type="email" id="mobileLoginEmail" placeholder="Nhập email" value="nep94121@gmail.com" required />
  26:   </div>
  27:   <div>
  28:     <label class="muted" for="mobileLoginPassword" style="display:block;margin-bottom:4px;">Mật khẩu</label>
  29:     <input type="password" id="mobileLoginPassword" placeholder="Nhập mật khẩu" value="123456" required />
  30:   </div>
  31:   <div id="mobileLoginMsg" class="muted" style="min-height:18px;"></div>
  32:   <button type="submit" class="btn primary" id="mobileLoginBtn">Đăng nhập</button>
  33: </form>
  ```
  - Mobile đã bọc `<form>` và hỗ trợ Enter, nhưng không có nút 👁️ Hiện/Ẩn mật khẩu.
  - Mobile chưa có tab Đặt/Đổi mật khẩu với 2 ô xác nhận mật khẩu đồng bộ như trên Web.
- **Tệp:** [simulator/auth_3layer.py](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/auth_3layer.py#L450-L455)
  - Backend `register_or_update_password` và `reset_password_with_otp` đã có sẵn logic kiểm tra bắt buộc 2 ô mật khẩu:
  ```python
  450: if not pw1 or not pw2:
  451:     return {"ok": False, "error": "Vui lòng nhập đầy đủ cả 2 ô: Mật khẩu và Xác nhận lại mật khẩu!"}
  452: if pw1 != pw2:
  453:     return {"ok": False, "error": "Hai ô mật khẩu (Mật khẩu và Xác nhận lại mật khẩu) không khớp nhau!"}
  ```

### 1.4. Lỗi SVG Sprite Bị Ẩn Trong `mobile_app/index.html`
- **Tệp:** [mobile_app/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/mobile_app/index.html#L15-L51)
  ```html
  15: <div id="mobileLoginGate" class="login-gate">
  16:   <div class="login-card">
  17:     <div class="login-header">
  18:       <svg class="icon" style="width:32px;height:32px;color:var(--accent)"><use href="#i-home"/></svg>
  19:       <h1 style="font-size:20px;margin-top:8px;">Nhà thông minh</h1>
  ...
  38: <div id="mobileMainContent" hidden>
  39: <svg width="0" height="0" style="position:absolute;visibility:hidden" aria-hidden="true">
  40:   <symbol id="i-home" viewBox="0 0 24 24"><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/></symbol>
  ...
  ```
- **Hiện tượng:** Icon `#i-home` được dùng ở dòng 18 bên trong `#mobileLoginGate`. Tuy nhiên, thẻ `<svg>` chứa định nghĩa `<symbol id="i-home">` lại nằm ở dòng 39 bên trong `<div id="mobileMainContent" hidden>`. Vì `#mobileMainContent` bị gán thuộc tính `hidden` khi chưa đăng nhập, khối SVG symbol không được trình duyệt render hoặc tính toán viewBox hợp lệ, dẫn đến icon ngôi nhà trên Cổng đăng nhập Mobile bị trắng/vỡ icon.

---

### 1.5. Lỗi `container.innerHTML = ""` Làm Mất `#house3dLabels` và `.viewport-note`
- **Tệp:** [simulator/static/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/index.html#L86-L92)
  ```html
  86: <div id="house3dViewport" class="viewport" role="img" aria-label="Vị trí mô hình 3D Toàn cảnh">
  87:   <div id="house3dLabels" class="house3d-labels"></div>
  88:   <span class="viewport-note">
  89:     <span class="note-desktop">Kéo để xoay · Cuộn để phóng to</span>
  90:     <span class="note-mobile">Kéo để xoay</span>
  91:   </span>
  92: </div>
  ```
- **Tệp:** [simulator/static/house3d.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/house3d.js#L153-L181)
  ```javascript
  153: function init(canvasContainerId, overlayLabelsId, onToggleDevice) {
  154:   container = document.getElementById(canvasContainerId);
  155:   labelsContainer = document.getElementById(overlayLabelsId);
  ...
  179:   container.innerHTML = "";
  180:   container.appendChild(renderer.domElement);
  181: 
  182:   buildLighting();
  ...
  186:   buildFloatingPins();
  ```
- **Hiện tượng:** 
  - Tại dòng 155, `labelsContainer` lấy tham chiếu tới phần tử `#house3dLabels`.
  - Tại dòng 179, lệnh `container.innerHTML = ""` xóa sạch mọi phần tử con bên trong `#house3dViewport`, bao gồm cả `#house3dLabels` và `.viewport-note`.
  - Kết quả: `#house3dLabels` bị tách rời khỏi DOM tree (detached DOM node). Mặc dù hàm `buildFloatingPins()` ở dòng 186 tiếp tục tạo ra 12 phần tử `<button class="pin-3d">` và gọi `labelsContainer.appendChild(el)`, những phần tử này không bao giờ xuất hiện trên màn hình vì cha của chúng đã bị xóa khỏi tài liệu HTML! Hướng dẫn `.viewport-note` cũng biến mất hoàn toàn.

---

### 1.6. Quy Tắc Ẩn Icon `.pin-3d .pin-icon` trong `style.css`
- **Tệp:** [simulator/static/css/style.css](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/css/style.css#L441-L447)
  ```css
  441: .pin-3d .pin-icon {
  442:   display: none !important;
  443: }
  444: 
  445: .pin-3d[title*="Bấm để chuyển góc nhìn"] {
  446:   display: none !important;
  447: }
  ```
- **Hiện tượng:**
  - Quy tắc dòng 441 ép ẩn toàn bộ icon emoji (`🚪`, `💡`, `🌀`, `❄️`, `🛏️`, `🚨`, `💧`).
  - Quy tắc dòng 445 ép ẩn toàn bộ các nút nhãn cảm biến & mạch điều khiển.
  - Danh mục 7 nút thiết bị nổi trong [simulator/static/house3d.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/house3d.js#L138-L145):
    1. `main_door`: `🚪` Cửa chính (D1)
    2. `living_room_light`: `💡` Đèn khách (D2)
    3. `fan`: `🌀` Quạt trần (D6)
    4. `ac`: `❄️` Điều hòa (D2 IR)
    5. `bedroom_light`: `🛏️` Đèn ngủ (D7)
    6. `alarm_siren`: `🚨` Còi báo động (D8)
    7. `garden_pump`: `💧` Máy bơm vườn (D3)
  - Khi click vào các nút này, `buildFloatingPins()` đã gắn listener gọi `onDeviceClickCallback(m.id)` (kết nối trực tiếp tới hàm `toggleDeviceById(id)` trong `app.js`).

---

### 1.7. Thanh Nút Chọn Góc Nhìn Camera 3D & Preset trong `house3d.js`
- **Tệp:** [simulator/static/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/index.html#L82-L85)
  ```html
  82: <div class="panel-head">
  83:   <h2 id="house-title">Ngôi nhà</h2>
  84:   <span class="view-label">Toàn cảnh</span>
  85: </div>
  ```
  Header của panel Ngôi nhà hiện chỉ có tiêu đề và nhãn tĩnh, hoàn toàn chưa có thanh nút bấm chuyển góc nhìn.
- **Tệp:** [simulator/static/house3d.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/house3d.js#L1274-L1294)
  Hàm `setCameraView(preset)` đã hỗ trợ đầy đủ 7 góc nhìn được tính toán tọa độ nội suy mượt:
  - `overview`: Toàn cảnh (`theta: 0.44, phi: 0.94, radius: 14.8`)
  - `living`: Phòng khách (`theta: 0.25, phi: 1.02, radius: 8.5`)
  - `bedroom`: Phòng ngủ (`theta: -0.35, phi: 0.98, radius: 9.0`)
  - `door`: Cửa chính (`theta: 0.12, phi: 1.12, radius: 6.8`)
  - `garden`: Sân vườn (`theta: -0.28, phi: 1.05, radius: 6.2`)
  - `board`: Mạch ESP (`theta: -0.45, phi: 0.98, radius: 4.6`)
  - `rotate`: Tự xoay (`camGoal.autoRotate = !camState.autoRotate`)
  Hàm này đã được export tại dòng 1648 (`SmartHome3D.setCameraView`).

---

### 1.8. Khảo Sát Tích Hợp `THREE.Raycaster` Cho Mesh 3D
- **Tệp:** [simulator/static/house3d.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/house3d.js#L1241-L1272)
  Hiện tại `bindMouseControls()` chỉ xử lý kéo xoay (drag) và cuộn chuột phóng to (wheel). Chưa có đối tượng `THREE.Raycaster`.
  Khi người dùng click chuột trực tiếp vào cánh cửa 3D (`doorPanel`), bóng đèn 3D (`lrBulb`), quạt trần 3D (`fanBladesGroup`), máy điều hòa (`acBody`), đèn ngủ (`bedCeilingLamp`), còi báo động (`sirenMesh`), hoặc máy bơm/bồn cây (`soilBed`), Three.js chưa bắt được sự kiện click để bật/tắt thiết bị tương ứng.

---

## 2. Logic Chain (Chuỗi Lập Luận Từ Quan Sát Đến Giải Pháp)

```
[Quan sát 1.1: Nút X tồn tại & đóng modal khi chưa xác thực]
  ──> Người dùng có thể bypass Login Gate hoàn toàn
  ──> Cần logic: Nếu !session -> ẩn nút X (#btnCloseLoginGateModal), vô hiệu hóa đóng ngoài lề (backdrop / ESC).
      Chỉ hiển thị nút X khi user đã đăng nhập hợp lệ và chủ động mở lại modal.

[Quan sát 1.2: auth.js lines 56 & 60 gán readOnly = true khi chọn Cấp 1]
  ──> Người dùng bị khóa ô input họ tên và email, không thể tùy chỉnh
  ──> Cần bỏ readOnly = true để người dùng chỉnh sửa tự do.

[Quan sát 1.3: Web dùng <div> thay vì <form>, thiếu nút 👁️ toggle type; Mobile thiếu 👁️ và chưa đồng bộ 2 ô xác nhận]
  ──> Trải nghiệm gõ phím Enter bị liệt trên Web; người dùng không kiểm tra được mật khẩu vừa gõ
  ──> Cần bọc <form> với listener submit, bổ sung button 👁️ (password <-> text) và đồng bộ luồng 2 ô xác nhận mật khẩu.

[Quan sát 1.4: mobile_app/index.html đặt SVG symbol trong #mobileMainContent hidden]
  ──> #mobileLoginGate không render được icon #i-home
  ──> Đưa khối <svg> sprite ra ngay sau thẻ <body> giúp icon khả dụng toàn cục trong mọi trạng thái đăng nhập.

[Quan sát 1.5: house3d.js line 179 dùng container.innerHTML = ""]
  ──> Xóa mất #house3dLabels và .viewport-note khỏi DOM, biến các nút nổi .pin-3d thành detached nodes
  ──> Thay bằng việc chỉ xóa <canvas> cũ và dùng container.insertBefore(renderer.domElement, container.firstChild) để bảo toàn 100% #house3dLabels và .viewport-note.

[Quan sát 1.6: style.css line 441 ẩn .pin-icon]
  ──> Các nút nổi mất icon nhận diện trực quan
  ──> Xóa bỏ rule display: none !important để hiển thị đầy đủ icon + tên + trạng thái BẬT/TẮT.

[Quan sát 1.7: house3d.js đã có setCameraView 7 presets nhưng HTML thiếu thanh nút]
  ──> Thêm thanh nút bấm tại header panel Ngôi nhà và gắn click listener gọi SmartHome3D.setCameraView.

[Quan sát 1.8: house3d.js chưa có THREE.Raycaster và cơ chế phân biệt Drag vs Click]
  ──> Thêm THREE.Raycaster, gán userData.deviceId trên các mesh thiết bị, đo khoảng cách di chuyển chuột (threshold ~6px) để kích hoạt toggleDevice khi click thật.
```

---

## 3. Caveats (Ranh Giới, Giả Định & Vùng Không Thuộc Khảo Sát)
1. **Phạm vi khảo sát là Read-Only:** Bản khảo sát này không chỉnh sửa trực tiếp mã nguồn ứng dụng trong Phase 0; toàn bộ thay đổi được đề xuất bằng diff snippet cụ thể cho giai đoạn triển khai (Implementation Phase).
2. **Kiểm thử đối kháng DOM:** Tệp `tests/test_challenger_m4_dom.py` quét toàn bộ selector ID giữa HTML và JS. Bất kỳ ID hoặc nút mới nào thêm vào HTML/JS đều phải tuân thủ nghiêm ngặt chuẩn định danh và null-safe guard để không làm gãy 36 test DOM hiện hành.
3. **Môi trường Three.js:** Thư viện Three.js trong dự án là bản vendor offline (`simulator/static/vendor/three.min.js`), phiên bản r128, đã hỗ trợ đầy đủ `THREE.Raycaster`, `THREE.Vector2`, và `THREE.PerspectiveCamera`.

---

## 4. Conclusion (Danh Mục Tính Năng, Rủi Ro & Đề Xuất Giải Pháp)

### 4.1. Bảng Tổng Hợp Tính Năng Cần Thực Hiện
| STT | Tính Năng / Vá Lỗi | Vị Trí Tệp | Mức Độ Ưu Tiên | Giải Pháp Kỹ Thuật |
|---|---|---|---|---|
| **F1** | Khóa cứng Login Gate, ẩn nút `X` khi chưa đăng nhập | `simulator/static/index.html`<br>`simulator/static/js/app.js` | 🔴 Khẩn cấp (Security Gate) | Ẩn `#btnCloseLoginGateModal` nếu chưa có session; chặn đóng modal qua backdrop; tự động mở modal khi chưa đăng nhập. |
| **F2** | Mở khóa ô nhập Họ tên & Email trong `auth.js` | `simulator/static/js/auth.js` | 🟡 Cao (UX) | Bỏ `readOnly = true` ở dòng 56 & 60, hỗ trợ người dùng chỉnh sửa tự do. |
| **F3** | Bọc `<form>`, hỗ trợ phím Enter & Nút 👁️ Hiện/Ẩn mật khẩu | `simulator/static/index.html`<br>`mobile_app/index.html`<br>`simulator/static/js/app.js`<br>`simulator/static/js/mobile_app.js` | 🟡 Cao (UX) | Chuyển `gatePanelLogin`, `gatePanelRegister`, `gatePanelForgot` thành thẻ `<form>`, thêm nút 👁️ chuyển đổi `type="password" <-> "text"`. |
| **F4** | Sửa vị trí khối SVG Icon trong `mobile_app/index.html` | `mobile_app/index.html` | 🟡 Cao (UI Visual) | Chuyển thẻ `<svg>` chứa các `<symbol>` ra ngoài `<div id="mobileMainContent" hidden>`, đặt ngay sau `<body>`. |
| **F5** | Bảo tồn `#house3dLabels` và `.viewport-note` trong `house3d.js` | `simulator/static/house3d.js` | 🔴 Khẩn cấp (3D Core) | Bỏ `container.innerHTML = ""`, chỉ xóa `<canvas>` cũ và dùng `container.insertBefore(renderer.domElement, container.firstChild)`. |
| **F6** | Hiển thị đầy đủ 7 nút nổi `.pin-3d` (Icon + Tên + BẬT/TẮT) | `simulator/static/css/style.css` | 🟡 Cao (3D UI) | Bỏ `.pin-3d .pin-icon { display: none !important; }` và rule ẩn nút cảm biến, tinh chỉnh CSS hiển thị đẹp mắt. |
| **F7** | Bổ sung thanh nút Camera 3D trên Panel Ngôi nhà | `simulator/static/index.html`<br>`simulator/static/js/app.js`<br>`simulator/static/css/style.css` | 🟢 Trung bình (Feature) | Thêm nhóm nút chọn góc nhìn (`Toàn cảnh`, `Phòng khách`, `Phòng ngủ`, `Cửa chính`, `Sân vườn`, `Mạch ESP`, `Tự xoay`) kết nối tới `SmartHome3D.setCameraView`. |
| **F8** | Tích hợp `THREE.Raycaster` tương tác click vào vật thể 3D | `simulator/static/house3d.js` | 🟡 Cao (Interactive 3D) | Gán `userData.deviceId` cho các mesh thiết bị, phân biệt drag xoay camera vs click (khoảng cách <= 6px) để gọi `onToggleDevice`. |

---

### 4.2. Đề Xuất Mã Nguồn Chi Tiết (Before -> After Snippets)

#### [F1 & F3] `simulator/static/index.html`
```html
<!-- TRƯỚC (BEFORE): Dòng 230 và các khối panel dạng div không có form -->
<button id="btnCloseLoginGateModal" type="button" class="btn-close" aria-label="Đóng">
  <svg class="icon"><use href="#i-x"/></svg>
</button>
...
<div id="gatePanelLogin" style="display:grid; gap:10px;">
  ...
  <input type="password" id="gateLoginPassword" ... />
  <button type="button" id="btnSubmitGateLogin" class="btn btn-primary" style="width:100%;">Đăng nhập</button>
</div>

<!-- SAU (AFTER): Nút X có hidden mặc định khi chưa auth, bọc form và thêm nút eye -->
<button id="btnCloseLoginGateModal" type="button" class="btn-close" aria-label="Đóng" hidden>
  <svg class="icon"><use href="#i-x"/></svg>
</button>
...
<form id="gatePanelLogin" style="display:grid; gap:10px;" onsubmit="event.preventDefault();">
  <div>
    <label for="gateLoginEmail" class="subtle" style="display:block; margin-bottom:4px;">Email đăng nhập</label>
    <input type="email" id="gateLoginEmail" class="input-text" style="width:100%;" value="nep94121@gmail.com" />
  </div>
  <div>
    <label for="gateLoginPassword" class="subtle" style="display:block; margin-bottom:4px;">Mật khẩu trong phần mềm</label>
    <div style="position:relative; display:flex; align-items:center;">
      <input type="password" id="gateLoginPassword" class="input-text" style="width:100%; padding-right:38px;" value="123456" />
      <button type="button" class="btn-toggle-pw" onclick="togglePasswordVisibility('gateLoginPassword', this)" style="position:absolute; right:8px; background:none; border:none; cursor:pointer;" aria-label="Hiện mật khẩu">👁️</button>
    </div>
  </div>
  <button type="submit" id="btnSubmitGateLogin" class="btn btn-primary" style="width:100%;">Đăng nhập vào Nhà thông minh</button>
</form>
```

#### [F1] `simulator/static/js/app.js`
```javascript
// TRƯỚC (BEFORE): Dòng 1438-1446
try {
  const savedRaw = window.localStorage ? window.localStorage.getItem("smarthome_auth_session") : null;
  const forceLoginModal = window.location && window.location.search && window.location.search.includes("login=1");
  if (savedRaw && !forceLoginModal) {
    applyLoggedInUserBanner(JSON.parse(savedRaw));
  } else if (forceLoginModal || (typeof navigator !== "undefined" && navigator.webdriver === false && window.localStorage)) {
    openLoginGateModal();
  }
} catch (_) {}

// SAU (AFTER): Kiểm tra khóa cứng phiên đăng nhập & quản lý nút X
try {
  const savedRaw = window.localStorage ? window.localStorage.getItem("smarthome_auth_session") : null;
  const user = savedRaw ? JSON.parse(savedRaw) : null;
  if (user && user.email) {
    applyLoggedInUserBanner(user);
    if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = false;
  } else {
    if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = true;
    openLoginGateModal();
  }
} catch (_) {
  openLoginGateModal();
}
```

#### [F2] `simulator/static/js/auth.js`
```javascript
// TRƯỚC (BEFORE): Dòng 52-61
if (selectedEnrollTier === 1) {
  selectedSpeakerName = 'Nguyễn Tuấn Anh';
  if (nameInput) {
    nameInput.value = 'Nguyễn Tuấn Anh';
    nameInput.readOnly = true;
  }
  if (emailInput) {
    emailInput.value = 'nep94121@gmail.com';
    emailInput.readOnly = true;
  }
  if (accSelect) accSelect.value = 'nep94121@gmail.com';
}

// SAU (AFTER): Cho phép người dùng chỉnh sửa tự do
if (selectedEnrollTier === 1) {
  selectedSpeakerName = (nameInput && nameInput.value.trim()) || 'Nguyễn Tuấn Anh';
  if (nameInput) {
    if (!nameInput.value) nameInput.value = 'Nguyễn Tuấn Anh';
    nameInput.readOnly = false;
  }
  if (emailInput) {
    if (!emailInput.value) emailInput.value = 'nep94121@gmail.com';
    emailInput.readOnly = false;
  }
  if (accSelect) accSelect.value = 'nep94121@gmail.com';
}
```

#### [F4] `mobile_app/index.html`
```html
<!-- TRƯỚC (BEFORE): Dòng 38-40 nằm sâu bên trong mobileMainContent hidden -->
<!-- NỘI DUNG CHÍNH (ẩn khi chưa đăng nhập) -->
<div id="mobileMainContent" hidden>
<svg width="0" height="0" style="position:absolute;visibility:hidden" aria-hidden="true">
  <symbol id="i-home" viewBox="0 0 24 24">...</symbol>

<!-- SAU (AFTER): Chuyển khối SVG lên ngay sau <body>, trước #mobileLoginGate -->
<body>
  <svg width="0" height="0" style="position:absolute;visibility:hidden" aria-hidden="true">
    <symbol id="i-home" viewBox="0 0 24 24"><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/></symbol>
    <symbol id="i-grid" viewBox="0 0 24 24">...</symbol>
    ...
  </svg>

  <!-- LOGIN GATE (icon #i-home luôn hiển thị chuẩn xác) -->
  <div id="mobileLoginGate" class="login-gate">
  ...
```

#### [F5] `simulator/static/house3d.js`
```javascript
// TRƯỚC (BEFORE): Dòng 179-180
container.innerHTML = "";
container.appendChild(renderer.domElement);

// SAU (AFTER): Chỉ xóa canvas cũ, chèn renderer xuống dưới các layer HTML nhãn nổi
const existingCanvas = container.querySelector("canvas");
if (existingCanvas) existingCanvas.remove();
container.insertBefore(renderer.domElement, container.firstChild);
```

#### [F6] `simulator/static/css/style.css`
```css
/* TRƯỚC (BEFORE): Dòng 441-447 */
.pin-3d .pin-icon {
  display: none !important;
}

.pin-3d[title*="Bấm để chuyển góc nhìn"] {
  display: none !important;
}

/* SAU (AFTER): Cho phép hiển thị icon nổi và nhãn cảm biến */
.pin-3d .pin-icon {
  display: inline-flex;
  align-items: center;
  font-size: 13px;
}

.pin-3d[title*="Bấm để chuyển góc nhìn"] {
  display: inline-flex;
  cursor: pointer;
}
```

#### [F7] Thêm Thanh Nút Camera trên Header Panel Ngôi Nhà
```html
<!-- Trong simulator/static/index.html: Dòng 82-85 -->
<div class="panel-head" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
  <div style="display:flex; align-items:center; gap:8px;">
    <h2 id="house-title">Ngôi nhà</h2>
    <span class="view-label" id="lblCurrentCameraView">Toàn cảnh</span>
  </div>
  <div class="camera-toolbar" style="display:flex; gap:4px; flex-wrap:wrap;">
    <button type="button" class="btn-cam active" data-cam="overview">Toàn cảnh</button>
    <button type="button" class="btn-cam" data-cam="living">Phòng khách</button>
    <button type="button" class="btn-cam" data-cam="bedroom">Phòng ngủ</button>
    <button type="button" class="btn-cam" data-cam="door">Cửa chính</button>
    <button type="button" class="btn-cam" data-cam="garden">Sân vườn</button>
    <button type="button" class="btn-cam" data-cam="board">Mạch ESP</button>
    <button type="button" class="btn-cam" data-cam="rotate">🔄 Tự xoay</button>
  </div>
</div>
```

#### [F8] Tích Hợp `THREE.Raycaster` trong `house3d.js`
```javascript
// Trong simulator/static/house3d.js:
const raycaster = new THREE.Raycaster();
const mouseVec = new THREE.Vector2();
const clickableMeshes = [];
let mouseDownPos = { x: 0, y: 0 };

function registerClickableMesh(mesh, deviceId) {
  if (!mesh) return;
  mesh.userData = mesh.userData || {};
  mesh.userData.deviceId = deviceId;
  clickableMeshes.push(mesh);
}

// Trong bindMouseControls():
dom.addEventListener("mousedown", (e) => {
  isDragging = true;
  mouseDownPos.x = e.clientX;
  mouseDownPos.y = e.clientY;
  prevMouse.x = e.clientX;
  prevMouse.y = e.clientY;
});

dom.addEventListener("mouseup", (e) => {
  isDragging = false;
  const dist = Math.hypot(e.clientX - mouseDownPos.x, e.clientY - mouseDownPos.y);
  if (dist <= 6) {
    // Click thật (không phải xoay camera)
    const rect = dom.getBoundingClientRect();
    mouseVec.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouseVec.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouseVec, camera);
    const intersects = raycaster.intersectObjects(clickableMeshes, true);
    if (intersects.length > 0) {
      let obj = intersects[0].object;
      while (obj && !obj.userData?.deviceId && obj !== scene) {
        obj = obj.parent;
      }
      if (obj && obj.userData?.deviceId && onDeviceClickCallback) {
        onDeviceClickCallback(obj.userData.deviceId);
      }
    }
  }
});
```

---

## 5. Verification Method (Phương Pháp Kiểm Chứng Độc Lập)

Người thực hiện hoặc reviewer độc lập có thể kiểm chứng báo cáo này theo các bước sau:

1. **Kiểm tra cú pháp & tính toàn vẹn DOM:**
   ```powershell
   pytest tests/test_challenger_m4_dom.py --basetemp=c:\Users\LENOVO\Desktop\pytest_temp_m4
   ```
   *Tiêu chí:* 36/36 tests đạt `PASSED` (Exit Code 0).

2. **Kiểm tra tính toàn vẹn 36 Luồng E2E:**
   ```powershell
   pytest tests/e2e/test_all_36_project_flows.py --basetemp=c:\Users\LENOVO\Desktop\pytest_temp_flows
   ```
   *Tiêu chí:* 36/36 tests đạt `PASSED` (Exit Code 0).

3. **Kiểm tra trực quan DOM bằng lệnh view_file / grep:**
   - Đối chiếu dòng 179 của [simulator/static/house3d.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/house3d.js#L179): `container.innerHTML = ""`
   - Đối chiếu dòng 441 của [simulator/static/css/style.css](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/css/style.css#L441): `.pin-3d .pin-icon { display: none !important; }`
   - Đối chiếu dòng 38-40 của [mobile_app/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/mobile_app/index.html#L38-L40): vị trí thẻ `<svg>` bên trong `#mobileMainContent`.
   - Đối chiếu dòng 56 & 60 của [simulator/static/js/auth.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/auth.js#L56): `nameInput.readOnly = true;`

Báo cáo khảo sát hoàn tất và sẵn sàng bàn giao cho Orchestrator để đưa vào Kế hoạch Thực thi Tổng thể (Implementation Plan).
