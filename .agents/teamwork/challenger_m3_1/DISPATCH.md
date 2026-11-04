## 2026-11-04T07:03:18Z
Bạn là Subagent teamwork_challenger (Challenger 1) thực hiện kiểm thử thực nghiệm đối kháng Milestone 3: 3D Model DOM, Controls & Raycaster.

MANDATORY: Đọc kỹ các tài liệu sau:
- File yêu cầu gốc của Sếp: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md`
- File kế hoạch dự án: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\PROJECT.md`
- Báo cáo bàn giao của Worker M3: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m3\handoff.md`

Thư mục làm việc của bạn: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\challenger_m3_1\`

Nhiệm vụ cụ thể:
1. Viết và thực thi một kịch bản kiểm thử đối kháng (adversarial test harness / script) trong thư mục làm việc của bạn để thử phá vỡ (stress-test / break) các tính năng vừa làm:
   - Thử nghiệm Raycaster: Phân biệt mousedown và mouseup với khoảng cách di chuyển chuột > 6px (drag xoay camera) vs <= 6px (click thiết bị). Kiểm tra xem kéo xoay có kích hoạt nhầm toggle không.
   - Thử nghiệm click Raycaster vào 7 thiết bị chấp hành (`main_door`, `living_room_light`, `fan`, `ac`, `bedroom_light`, `alarm_siren`, `garden_pump`).
   - Thử nghiệm DOM: Xác nhận `#house3dLabels` và `.viewport-note` không bị xóa bởi `container.innerHTML = ""`.
   - Thử nghiệm CSS: Xác nhận không còn `.pin-icon { display: none !important; }`.
   - Thử nghiệm 7 nút camera preset trên header panel Ngôi nhà: overview, living, bedroom, door, garden, board, rotate.
2. Chạy `python -m pytest tests/test_challenger_m4_dom.py -v --basetemp=.pytest_temp_chal_m3_1`.
3. Đưa ra kết luận thực nghiệm đối kháng rõ ràng: APPROVE hoặc REQUEST_CHANGES.

Viết báo cáo bàn giao chi tiết vào:
`c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\challenger_m3_1\handoff.md`
Khi hoàn tất, gửi tin nhắn báo cáo cho Orchestrator với verdict chính thức.
