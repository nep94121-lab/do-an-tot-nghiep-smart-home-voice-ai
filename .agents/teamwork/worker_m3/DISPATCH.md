## 2026-11-04T06:49:14Z

Bạn là Subagent teamwork_worker thực hiện Milestone 3: 3D Model DOM, Controls & Raycaster.

MANDATORY: Đọc kỹ các tài liệu sau trước khi thực hiện:
- File yêu cầu gốc của Sếp: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md`
- File kế hoạch dự án: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\PROJECT.md`
- Báo cáo khảo sát chi tiết của Explorer 2: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\survey_2\handoff.md`

Thư mục làm việc của bạn: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m3\`

Quyền sở hữu tệp (Write Ownership) ĐỘC QUYỀN của bạn:
1. `simulator/static/house3d.js`
2. `simulator/static/css/style.css`
3. `simulator/static/index.html` (chỉ sửa khu vực header panel Ngôi nhà 3D để thêm thanh nút camera)
4. `simulator/static/js/app.js` (gắn event listener cho thanh nút camera gọi `SmartHome3D.setCameraView`)
(TUYỆT ĐỐI KHÔNG sửa các file ngoài danh sách này).

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Nhiệm vụ cụ thể:
1. Sửa lỗi trong `simulator/static/house3d.js` dòng 179:
   - `container.innerHTML = ""` đang xóa mất `#house3dLabels` và `.viewport-note` bên trong `#house3dViewport`!
   - Sửa thành: chỉ xóa `<canvas>` cũ (nếu có) và dùng `container.insertBefore(renderer.domElement, container.firstChild)` để giữ nguyên vẹn `#house3dLabels` và `.viewport-note` nổi trên mô hình 3D.
2. Sửa file `simulator/static/css/style.css`:
   - Bỏ quy tắc `.pin-3d .pin-icon { display: none !important; }` (dòng 441) và rule ẩn nút cảm biến (dòng 445).
   - Tinh chỉnh CSS để 7 nút nổi `.pin-3d` trên 7 thiết bị hiển thị rõ icon emoji (`🚪`, `💡`, `🌀`, `❄️`, `🛏️`, `🚨`, `💧`) + tên thiết bị + trạng thái BẬT/TẮT và bấm vào bật/tắt trực tiếp thiết bị.
3. Thêm thanh nút chọn góc nhìn Camera 3D trên header của panel Ngôi nhà trong `simulator/static/index.html`:
   - Gồm 7 nút preset: `Toàn cảnh` (overview), `Phòng khách` (living), `Phòng ngủ` (bedroom), `Cửa chính` (door), `Sân vườn` (garden), `Mạch ESP` (board), `🔄 Tự xoay` (rotate).
   - Trong `simulator/static/js/app.js`: Gắn click event listener cho các nút này để gọi `SmartHome3D.setCameraView(preset)` và cập nhật class active/nhãn góc nhìn hiện tại.
4. Tích hợp `THREE.Raycaster` khi click vào mô hình 3D trong `simulator/static/house3d.js`:
   - Cơ chế phân biệt Kéo xoay camera (drag) vs Click thật: đo khoảng cách di chuyển chuột giữa mousedown và mouseup (`Math.hypot(dx, dy) <= 6px`).
   - Gán `userData.deviceId` cho các mesh/group của thiết bị 3D.
   - Khi click trúng mesh thiết bị, kích hoạt `onToggleDevice(deviceId)` để bật/tắt thiết bị tương ứng (đồng bộ với click trên nút nổi và bảng điều khiển).
5. Chạy kiểm thử xác thực:
   - `python -m pytest tests/test_challenger_m4_dom.py -v --basetemp=.pytest_temp_m3` (phải đạt 36/36 PASS, không làm vỡ DOM, không thiếu window exports).
   - Đảm bảo 100% POSIX LF (0 CRLF) và UTF-8 không BOM.

Viết báo cáo bàn giao chi tiết (bao gồm lệnh đã chạy, kết quả, file đã sửa, diff cụ thể) vào:
`c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m3\handoff.md`
Khi hoàn tất, gửi tin nhắn báo cáo cho Orchestrator kèm đường dẫn file bàn giao.
