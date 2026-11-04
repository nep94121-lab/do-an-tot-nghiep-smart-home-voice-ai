# Progress - Survey 2: Login Gate & Password UX & 3D Model DOM/Raycaster

Last visited: 2026-11-04T06:15:00Z
Status: Completed

## Tasks:
- [x] Đọc DISPATCH.md và ORIGINAL_REQUEST.md
- [x] Khảo sát Phần 1: Login Gate & Password UX (Web & Mobile)
  - [x] `#homeLoginGateModal` trong `simulator/static/index.html` và `simulator/static/js/app.js`
  - [x] Nút `X` (`#btnCloseLoginGateModal`), giải pháp ẩn/bỏ khi chưa đăng nhập
  - [x] Logic đăng nhập Email (`nep94121@gmail.com`) + Mật khẩu (`123456`)
  - [x] Các ô input `readOnly = true` trong `simulator/static/js/auth.js` (dòng 56, 60, 111)
  - [x] Form bọc `<form>`, Enter submit, nút 👁️ toggle password, 2 ô xác nhận mật khẩu (Web + Mobile)
  - [x] `mobile_app/index.html`: vị trí SVG `<symbol id="i-home">...` và `<div id="mobileMainContent" hidden>`
- [x] Khảo sát Phần 2: Giao diện Nút bấm & Thao tác Mô hình 3D
  - [x] `simulator/static/house3d.js` line 179: `container.innerHTML = ""` và `#house3dLabels`, `.viewport-note`
  - [x] `simulator/static/css/style.css`: `.pin-3d .pin-icon { display: none !important; }` và cấu trúc 7 nút nổi
  - [x] Thanh nút camera 3D (`Toàn cảnh`, `Phòng khách`, `Phòng ngủ`, `Cửa chính`, `Sân vườn`, `Mạch ESP`, `Tự xoay`)
  - [x] Tích hợp `THREE.Raycaster` click trực tiếp vào mesh 3D
- [x] Lập bảng so sánh, rủi ro, ràng buộc kỹ thuật và đề xuất giải pháp chi tiết
- [x] Soạn thảo và hoàn thiện `handoff.md` theo cấu trúc 5 thành phần
- [x] Gửi thông báo hoàn tất cho Orchestrator
