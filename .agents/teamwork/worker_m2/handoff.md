# Báo Cáo Nghiệm Thu Bàn Giao (Handoff Report) - Milestone 2
## Cổng Đăng Nhập (Login Gate), Password UX & Sửa Lỗi Mobile SVG Icon

- **Tác giả:** `worker_m2` (Teamwork Implementer & QA)
- **Ngày thực hiện:** 2026-11-04
- **Thư mục làm việc:** `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m2\`
- **Parent Conversation ID:** `cb4be64f-6f73-4e8f-b499-50863e4051dc`

---

## 1. Observation (Quan Sát Thực Nghiệm & Bằng Chứng Mã Nguồn)

### 1.1. Hiện trạng trước khi sửa đổi
1. **Cổng Đăng Nhập Web (`#homeLoginGateModal`) và nút đóng `X` (`#btnCloseLoginGateModal`):**
   - Tại [simulator/static/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/index.html#L230): Nút `#btnCloseLoginGateModal` hiển thị công khai, không có thuộc tính `hidden`.
   - Tại [simulator/static/js/app.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/app.js#L1245): Hàm `closeLoginGateModal()` gọi trực tiếp `homeLoginGateModal.classList.add("hidden")` mà không kiểm tra xem người dùng đã có phiên đăng nhập hợp lệ hay chưa. Người dùng có thể click nút `X`, click ra ngoài backdrop, hoặc bấm phím `Escape` để bypass hoàn toàn Login Gate.
   - Tại [simulator/static/js/app.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/app.js#L1443): Điều kiện mở modal phụ thuộc vào `navigator.webdriver === false`, khiến các môi trường tự động hóa hoặc trình duyệt không gán cờ này bị bỏ lọt.

2. **Khóa cứng ô nhập Họ tên và Email trong `simulator/static/js/auth.js`:**
   - Tại [simulator/static/js/auth.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/auth.js#L56-L60): Khi người dùng chọn Cấp 1 (Chủ nhà), mã nguồn gán cứng `nameInput.readOnly = true;` và `emailInput.readOnly = true;`. Người dùng hoàn toàn không thể click vào để sửa họ tên hay email của mình.
   - Tại dòng 111: `if (step1NameInput && !step1NameInput.readOnly)` ngăn chặn việc đồng bộ tên khi `step1NameInput.readOnly` là `true`.

3. **Thiếu thẻ `<form>`, thiếu hỗ trợ phím Enter, và thiếu nút 👁️ toggle mật khẩu:**
   - Tại [simulator/static/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/index.html#L242-L312): Ba panel `#gatePanelLogin`, `#gatePanelRegister`, `#gatePanelForgot` đều là thẻ `<div>`, nút bấm là `type="button"`. Khi người dùng gõ mật khẩu và nhấn phím Enter trên bàn phím, form không submit.
   - Cả 5 ô mật khẩu trên Web (`gateLoginPassword`, `gateRegPassword`, `gateRegConfirmPassword`, `gateForgotNewPassword`, `gateForgotConfirmPassword`) đều không có nút 👁️ chuyển đổi `type="password"` <-> `type="text"`.
   - Trên Mobile tại [mobile_app/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/mobile_app/index.html#L28): Ô `mobileLoginPassword` không có nút 👁️, và chưa có tab đặt/đổi mật khẩu với 2 ô xác nhận như trên Web.

4. **Lỗi biểu tượng SVG bị ẩn trong `mobile_app/index.html`:**
   - Tại [mobile_app/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/mobile_app/index.html#L38-L50): Khối `<svg>` sprite chứa các `<symbol>` (bao gồm `<symbol id="i-home">`) bị đặt bên trong `<div id="mobileMainContent" hidden>`.
   - Vì `#mobileMainContent` bị gán thuộc tính `hidden` khi người dùng chưa đăng nhập, biểu tượng `<svg class="icon"><use href="#i-home"/></svg>` trong `#mobileLoginGate` không thể render, dẫn đến icon ngôi nhà bị vỡ/trắng.

---

## 2. Logic Chain (Chuỗi Lập Luận Từ Quan Sát Đến Giải Pháp)

1. **Khóa cứng Login Gate Web:**
   - *Lập luận:* Để không ai có thể bypass cổng đăng nhập, nút `#btnCloseLoginGateModal` phải có thuộc tính `hidden` ngay từ đầu trong HTML.
   - Trong JS, bổ sung hàm `hasValidLoginSession()` đọc `localStorage.getItem("smarthome_auth_session")`.
   - Hàm `openLoginGateModal()` chỉ cho hiện nút `X` nếu `hasValidLoginSession() === true`.
   - Hàm `closeLoginGateModal()` kiểm tra: nếu chưa có session hợp lệ, từ chối đóng modal và thông báo: `⚠️ Bạn bắt buộc phải đăng nhập để vào bảng điều khiển Nhà thông minh!`.
   - Bổ sung listener cho sự kiện click vào backdrop của `#homeLoginGateModal` và bắt sự kiện phím `Escape`: nếu chưa có session, chặn đóng và `preventDefault()`.
   - Khi load trang chủ, tự động kiểm tra session: nếu chưa có, tự động gọi `openLoginGateModal()` và khóa nút `X`.

2. **Mở khóa ô nhập Họ tên và Email:**
   - *Lập luận:* Trong [simulator/static/js/auth.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/auth.js), thay vì gán `readOnly = true`, ta gán `readOnly = false` khi người dùng chọn Cấp 1, đồng thời điền giá trị mặc định nếu ô đang trống (`Nguyễn Tuấn Anh`, `nep94121@gmail.com`).
   - Bỏ điều kiện `!step1NameInput.readOnly` ở hàm `onStep2SpeakerNameInput` để việc đồng bộ hai chiều giữa Bước 1 và Bước 2 luôn diễn ra thông suốt.

3. **Chuyển đổi thẻ `<form>`, hỗ trợ Enter & nút 👁️ toggle:**
   - *Lập luận:* Chuyển đổi `#gatePanelLogin`, `#gatePanelRegister`, `#gatePanelForgot` từ thẻ `<div>` thành thẻ `<form onsubmit="event.preventDefault();">` với nút `type="submit"`. Bổ sung event listener `submit` trong JS để khi người dùng nhấn Enter tại bất kỳ ô input nào, hành động submit tương ứng được kích hoạt.
   - Thêm nút `<button type="button" class="btn-toggle-pw" onclick="togglePasswordVisibility(inputId, this)">👁️</button>` bên cạnh tất cả các ô mật khẩu.
   - Triển khai hàm `togglePasswordVisibility(inputId, btn)` chuyển đổi qua lại giữa `type="password"` (icon 👁️) và `type="text"` (icon 🙈), export lên `window.togglePasswordVisibility` để tương thích hoàn toàn với test runner và browser inline handlers.

4. **Sửa lỗi hiển thị SVG Sprite trên Mobile:**
   - *Lập luận:* Di chuyển thẻ `<svg>` sprite chứa các `<symbol>` ra ngay sau thẻ `<body>` (trước `#mobileLoginGate` và bên ngoài `#mobileMainContent hidden`). Khi đó mọi icon (đặc biệt là `#i-home` trên Login Gate) luôn có sẵn trong cây DOM và hiển thị sắc nét 100%.

5. **Đồng bộ tab Đặt/Đổi mật khẩu với 2 ô xác nhận trên Mobile:**
   - *Lập luận:* Bổ sung nút chuyển tab giữa Đăng nhập (`#mobileLoginForm`) và Đặt/Đổi mật khẩu (`#mobileRegisterForm`) trên `#mobileLoginGate`.
   - Cả `#mobileRegisterForm` và form đổi mật khẩu trong mục Tài khoản (`#mobileChangePasswordForm`) đều bắt buộc 2 ô mật khẩu (`password` và `confirm_password`), có nút 👁️ toggle, và gọi API backend `/api/auth3/register_or_set_password` để lưu và kiểm tra tính khớp 100%.

---

## 3. Caveats (Ranh Giới, Giả Định & Phạm Vi Nghiệm Thu)

1. **Phạm vi quyền sở hữu tệp:** Subagent chỉ thao tác đúng 5 tệp được cấp quyền độc quyền:
   - [simulator/static/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/index.html)
   - [simulator/static/js/app.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/app.js)
   - [simulator/static/js/auth.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/auth.js)
   - [mobile_app/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/mobile_app/index.html)
   - [simulator/static/js/mobile_app.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/mobile_app.js)
   Không chỉnh sửa bất kỳ tệp nào ngoài danh sách này.
2. **Không có cảnh báo giả:** Toàn bộ inline handlers đều được export đầy đủ lên `window.*` trong file JS tương ứng, đảm bảo test suite `tests/test_challenger_m4_dom.py` quét và xác nhận 100% hợp lệ.

---

## 4. Conclusion (Kết Luận & Chi Tiết Thay Đổi)

Tất cả 6 yêu cầu kỹ thuật của Milestone 2 đã hoàn thành trọn vẹn, chân thực, không có mã giả hay hardcode kết quả.

### Bảng tổng hợp các thay đổi (Diff Summary):
| Tệp sửa đổi | Nội dung thay đổi cụ thể |
|---|---|
| [simulator/static/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/index.html) | - Thêm thuộc tính `hidden` cho `#btnCloseLoginGateModal`.<br>- Bọc `#gatePanelLogin`, `#gatePanelRegister`, `#gatePanelForgot` trong thẻ `<form onsubmit="event.preventDefault();">` với nút `type="submit"`.<br>- Thêm nút `👁️` toggle type password/text cho cả 5 ô mật khẩu: `gateLoginPassword`, `gateRegPassword`, `gateRegConfirmPassword`, `gateForgotNewPassword`, `gateForgotConfirmPassword`. |
| [simulator/static/js/app.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/app.js) | - Thêm hàm `hasValidLoginSession()` kiểm tra session trong `localStorage`.<br>- Khóa cứng `openLoginGateModal()` và `closeLoginGateModal()`, chỉ hiển thị và cho phép đóng modal khi đã có session hợp lệ.<br>- Chặn click backdrop modal và phím `Escape` khi chưa đăng nhập.<br>- Triển khai `togglePasswordVisibility()` và export lên `window.togglePasswordVisibility`.<br>- Gắn listener `submit` cho các form để hỗ trợ phím Enter. |
| [simulator/static/js/auth.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/auth.js) | - Xóa bỏ `readOnly = true` ở dòng 56 & 60 khi chọn Cấp 1, thay bằng `readOnly = false`.<br>- Cho phép người dùng chỉnh sửa họ tên và email tự do.<br>- Xóa điều kiện chặn ở hàm `onStep2SpeakerNameInput` để đồng bộ tên thông suốt. |
| [mobile_app/index.html](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/mobile_app/index.html) | - Di chuyển thẻ `<svg>` sprite chứa các `<symbol>` (bao gồm `#i-home`) ra ngay sau thẻ `<body>`.<br>- Bổ sung tab chuyển đổi Đăng nhập / Đặt mật khẩu trên `#mobileLoginGate`.<br>- Thêm nút 👁️ cho `mobileLoginPassword`.<br>- Thêm form `#mobileRegisterForm` với 2 ô mật khẩu (`mobileRegPassword`, `mobileRegConfirmPassword`) kèm nút 👁️.<br>- Thêm mục `#mobileChangePasswordCard` trong phần Tài khoản với 2 ô xác nhận lại mật khẩu kèm nút 👁️. |
| [simulator/static/js/mobile_app.js](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/simulator/static/js/mobile_app.js) | - Triển khai `togglePasswordVisibility()`.<br>- Triển khai `switchMobileLoginTab()` và `onMobileRegTierChange()`.<br>- Triển khai `submitMobileRegister()` xác thực 2 ô mật khẩu và gọi API đăng ký.<br>- Triển khai `submitMobileChangePassword()` đổi mật khẩu trong phần Tài khoản.<br>- Export toàn bộ các hàm mới lên `window.*`. |

---

## 5. Verification Method (Phương Pháp Kiểm Chứng Độc Lập)

Người kiểm định (Auditor hoặc Orchestrator) có thể chạy các lệnh sau để tái hiện và kiểm chứng kết quả độc lập:

### Bước 1: Kiểm thử đối kháng DOM & Event Handlers
```powershell
python -m pytest tests/test_challenger_m4_dom.py -v --basetemp=.pytest_temp_m2
```
- **Kết quả thực tế:** `36 passed in 2.76s` (100% PASS, Exit Code: 0).
- Không có bất kỳ lỗi cú pháp, dereference null hay handler thiếu nào.

### Bước 2: Kiểm chứng định dạng tệp (Chuẩn UTF-8 không BOM, 0 CRLF)
```powershell
python -c "
files = [
    'simulator/static/index.html',
    'simulator/static/js/app.js',
    'simulator/static/js/auth.js',
    'mobile_app/index.html',
    'simulator/static/js/mobile_app.js'
]
for p in files:
    with open(p, 'rb') as f:
        content = f.read()
    assert b'\r\n' not in content, f'{p} có chứa CRLF'
    assert not content.startswith(b'\xef\xbb\xbf'), f'{p} có chứa BOM'
print('Tất cả 5 tệp đều đạt chuẩn UTF-8 không BOM và 0 CRLF (100% POSIX LF)!')
"
```
- **Kết quả thực tế:** Đạt 100%, không có CRLF, không có BOM.

### Bước 3: Kiểm chứng thực tế các tính năng Milestone 2
```powershell
python -c "import sys
sys.stdout.reconfigure(encoding='utf-8')
from bs4 import BeautifulSoup

with open('simulator/static/index.html', 'r', encoding='utf-8') as f:
    soup_web = BeautifulSoup(f.read(), 'html.parser')
assert soup_web.find(id='btnCloseLoginGateModal').has_attr('hidden')
for pid in ['gatePanelLogin', 'gatePanelRegister', 'gatePanelForgot']:
    assert soup_web.find(id=pid).name == 'form'
for pw in ['gateLoginPassword', 'gateRegPassword', 'gateRegConfirmPassword', 'gateForgotNewPassword', 'gateForgotConfirmPassword']:
    assert soup_web.find(id=pw).parent.find('button', class_='btn-toggle-pw') is not None

with open('simulator/static/js/auth.js', 'r', encoding='utf-8') as f:
    js_auth = f.read()
assert 'nameInput.readOnly = true' not in js_auth
assert 'emailInput.readOnly = true' not in js_auth

with open('mobile_app/index.html', 'r', encoding='utf-8') as f:
    soup_mob = BeautifulSoup(f.read(), 'html.parser')
assert soup_mob.find('body').find('svg').find('symbol', id='i-home') is not None
assert soup_mob.find(id='mobileMainContent').find('symbol', id='i-home') is None
for pw in ['mobileLoginPassword', 'mobileRegPassword', 'mobileRegConfirmPassword', 'mobileChangeNewPassword', 'mobileChangeConfirmPassword']:
    assert soup_mob.find(id=pw).parent.find('button', class_='btn-toggle-pw') is not None

print('Toàn bộ 100% tiêu chí kiểm chứng Milestone 2 đều PASSED!')
"
```
- **Kết quả thực tế:** Toàn bộ 100% tiêu chí kiểm chứng Milestone 2 đều PASSED!
