# BRIEFING — 2026-11-04T07:01:30Z

## Mission
Thực hiện Milestone 3: 3D Model DOM, Controls & Raycaster cho Simulator Smart Home 3D.

## 🔒 My Identity
- Archetype: subagent (teamwork_worker)
- Roles: implementer, qa
- Working directory: c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m3
- Original parent: cb4be64f-6f73-4e8f-b499-50863e4051dc
- Milestone: Milestone 3 - 3D Model DOM, Controls & Raycaster

## 🔒 Key Constraints
- Quyền sở hữu tệp ĐỘC QUYỀN:
  1. `simulator/static/house3d.js`
  2. `simulator/static/css/style.css`
  3. `simulator/static/index.html` (chỉ sửa khu vực header panel Ngôi nhà 3D để thêm thanh nút camera)
  4. `simulator/static/js/app.js` (gắn event listener cho thanh nút camera gọi `SmartHome3D.setCameraView`)
  (TUYỆT ĐỐI KHÔNG sửa các file ngoài danh sách này).
- DO NOT CHEAT: không hardcode kết quả, không tạo facade, giữ logic thật 100%.
- Định dạng file: 100% POSIX LF (\n), UTF-8 không BOM.
- Kiểm thử phải đạt 36/36 test case trong `tests/test_challenger_m4_dom.py`.

## Current Parent
- Conversation ID: cb4be64f-6f73-4e8f-b499-50863e4051dc
- Updated: 2026-11-04T07:01:30Z

## Task Summary
- **What to build**:
  1. Fix `house3d.js`: không xóa `#house3dLabels` và `.viewport-note`, chỉ xóa canvas cũ và chèn renderer xuống dưới (`container.insertBefore(renderer.domElement, container.firstChild)`).
  2. Fix `style.css`: bỏ `.pin-3d .pin-icon { display: none !important; }` và rule ẩn nút cảm biến, tinh chỉnh CSS hiển thị emoji, tên thiết bị, trạng thái ON/OFF và style `.camera-toolbar` / `.btn-cam`.
  3. Thêm 7 nút preset camera trên header panel trong `index.html` (`overview`, `living`, `bedroom`, `door`, `garden`, `board`, `rotate`) và logic trong `app.js` gọi `SmartHome3D.setCameraView(preset)` và cập nhật active class/label.
  4. Tích hợp `THREE.Raycaster` trong `house3d.js`: phân biệt drag vs click (< 6px), gán `userData.deviceId` cho 7 thiết bị, trigger `onToggleDevice(deviceId)` khi click vào mesh 3D.
  5. Chạy kiểm thử pytest `tests/test_challenger_m4_dom.py` (36/36 PASS), `test_all_36_project_flows.py` (36/36 PASS), và test độc lập `test_m3_orthogonal.py` (18/18 PASS).
- **Success criteria**: 36/36 DOM tests pass, 18/18 orthogonal tests pass, 0 CRLF, UTF-8 no BOM.
- **Interface contracts**: PROJECT.md, survey_2/handoff.md
- **Code layout**: `simulator/static/...`

## Change Tracker
- **Files modified**:
  1. `simulator/static/house3d.js`: Bảo tồn DOM labels qua insertBefore, tích hợp THREE.Raycaster + threshold <=6px, gán userData.deviceId cho 7 thiết bị, đồng bộ camera toolbar.
  2. `simulator/static/css/style.css`: Bỏ display:none trên .pin-icon, tối ưu hóa CSS 7 nút nổi .pin-3d và tạo kiểu cho camera-toolbar / btn-cam.
  3. `simulator/static/index.html`: Thay header tĩnh bằng 7 nút preset camera và nhãn lblCurrentCameraView.
  4. `simulator/static/js/app.js`: Thêm initCameraToolbar() lắng nghe click trên .btn-cam gọi SmartHome3D.setCameraView(preset).
- **Build status**: PASS (node -c cú pháp JS 0 lỗi, pytest 36/36 PASS)
- **Pending issues**: Không có

## Quality Status
- **Build/test result**:
  - `tests/test_challenger_m4_dom.py`: 36/36 PASSED
  - `tests/e2e/test_all_36_project_flows.py`: 36/36 PASSED
  - `test_m3_orthogonal.py`: 18/18 PASSED
- **Lint status**: 0 CRLF, 0 BOM, cú pháp chuẩn JS ES6 & HTML5/CSS3.
- **Tests added/modified**: `test_m3_orthogonal.py` (18 bài kiểm tra đối kháng độc lập).

## Loaded Skills
- Không có kỹ năng riêng cần nạp thêm.

## Artifact Index
- `.agents/teamwork/worker_m3/DISPATCH.md` — Chỉ thị dispatch
- `.agents/teamwork/worker_m3/BRIEFING.md` — Bộ nhớ làm việc
- `.agents/teamwork/worker_m3/progress.md` — Tiến độ công việc
- `.agents/teamwork/worker_m3/test_m3_orthogonal.py` — Script kiểm tra độc lập
- `.agents/teamwork/worker_m3/handoff.md` — Báo cáo bàn giao
