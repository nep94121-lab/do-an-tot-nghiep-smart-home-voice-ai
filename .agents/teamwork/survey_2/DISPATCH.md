## 2026-11-04T06:04:26Z
[From: cb4be64f-6f73-4e8f-b499-50863e4051dc (parent)]
Bạn là Subagent teamwork_explorer thực hiện nhiệm vụ Khảo sát Kỹ thuật (Survey Phase 0) - Mảng 2: Login Gate & Password UX & 3D Model DOM/Raycaster.

MANDATORY: Đọc kỹ file yêu cầu gốc của Sếp tại:
`c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md`

Thư mục làm việc của bạn: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\survey_2\`
(Chỉ ghi file báo cáo / metadata trong thư mục này, KHÔNG sửa mã nguồn hệ thống ở bước khảo sát).

Nhiệm vụ cụ thể:
1. Khảo sát Cổng Đăng nhập (Login Gate) & Ô nhập Mật khẩu:
   - Kiểm tra `#homeLoginGateModal` trong `simulator/static/index.html` và `simulator/static/js/app.js`.
   - Tìm nút `X` (`#btnCloseLoginGateModal`), cách ẩn/bỏ nút này khi chưa đăng nhập.
   - Kiểm tra logic đăng nhập Email (`nep94121@gmail.com`) + Mật khẩu (`123456`).
   - Kiểm tra các ô input trong `simulator/static/js/auth.js` (dòng 56, 60 và các nơi khác) đang bị `readOnly = true`.
   - Kiểm tra việc bọc thẻ `<form>` để hỗ trợ phím Enter, thêm nút 👁️ Hiện/Ẩn mật khẩu, và bắt buộc 2 ô xác nhận mật khẩu (password + confirm_password) trên cả Web và Mobile (`/app` hoặc `mobile_app/`).
   - Kiểm tra file `mobile_app/index.html`: vị trí khối `<svg>` chứa `<symbol id="i-home">...` và `<div id="mobileMainContent" hidden>`, giải pháp đưa SVG ra ngoài để icon hiển thị đúng trên `#mobileLoginGate`.
2. Khảo sát Giao diện Nút bấm & Thao tác Mô hình 3D:
   - Đọc và phân tích `simulator/static/house3d.js` dòng 179: hiện tượng `container.innerHTML = ""` xóa mất `#house3dLabels` và `.viewport-note` bên trong `#house3dViewport`.
   - Đọc `simulator/static/css/style.css`: tìm quy tắc `.pin-3d .pin-icon { display: none !important; }`, cấu trúc của 7 nút nổi `.pin-3d` (icon + tên + trạng thái BẬT/TẮT + click handler).
   - Kiểm tra thanh nút chọn góc nhìn Camera 3D (`Toàn cảnh`, `Phòng khách`, `Phòng ngủ`, `Cửa chính`, `Sân vườn`, `Mạch ESP`, `Tự xoay`) trên header panel Ngôi nhà 3D trong `simulator/static/index.html` và mã điều khiển camera tương ứng trong `house3d.js`.
   - Khảo sát việc tích hợp `THREE.Raycaster` để click trực tiếp vào mesh/vật thể 3D nhằm bật/tắt thiết bị tương ứng.
3. Lập danh mục Feature, rủi ro, ràng buộc kỹ thuật và đề xuất giải pháp chi tiết.

Viết báo cáo đầy đủ, chi tiết vào:
`c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\survey_2\handoff.md`
Khi hoàn tất, gửi tin nhắn báo cho Orchestrator với đường dẫn file báo cáo.
