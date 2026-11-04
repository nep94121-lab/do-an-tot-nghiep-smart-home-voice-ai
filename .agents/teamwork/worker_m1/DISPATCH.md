## 2026-11-04T06:20:00Z
Bạn là Subagent teamwork_worker thực hiện Milestone 1: Deployment & Connectivity (Vercel, HTTPS Tunnel, LAN IP & QR TOTP Extension).

MANDATORY: Đọc kỹ các tài liệu sau trước khi thực hiện:
- File yêu cầu gốc của Sếp: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md`
- File kế hoạch dự án: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\PROJECT.md`
- Báo cáo khảo sát chi tiết của Explorer 1: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\survey_1\handoff.md`

Thư mục làm việc của bạn: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m1\`

Quyền sở hữu tệp (Write Ownership) ĐỘC QUYỀN của bạn:
1. `vercel.json` (tạo mới ở thư mục gốc)
2. `simulator/auth/qr_totp_mixin.py`
3. `simulator/api/routes_qr.py`
4. `simulator/static/js/guest_enroll.js`
(TUYỆT ĐỐI KHÔNG sửa các file ngoài danh sách này).

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Nhiệm vụ cụ thể:
1. Tạo `vercel.json` định tuyến 6 trang static frontend (`/`, `/app`, `/auth`, `/guest_enroll`, `/logs`, `/wokwi`), static assets (`/static/`), test audio (`/test_audio/`), và tài liệu archify (`/archify`). Đẩy mã nguồn lên GitHub repo `nep94121-lab/do-an-tot-nghiep-smart-home-voice-ai` và chạy deploy Vercel (`vercel --prod --yes`).
2. Sửa `simulator/auth/qr_totp_mixin.py` hàm `consume_guest_handshake`: nới rộng cửa sổ thời gian chấp nhận token lên 180s (18 chu kỳ window) để khi quét mã QR trên điện thoại không bao giờ bị báo hết hạn 10s giữa chừng, đồng thời duy trì bảo vệ Single-Use Token (`store.add(clean_tok)`) chống Replay Attack.
3. Sửa `simulator/api/routes_qr.py`: đảm bảo hỗ trợ tham số `host` / `host_url`, tự động nhận diện tiền tố `https://` cho domain tunnel (như `*.lhr.life`).
4. Sửa `simulator/static/js/guest_enroll.js`: đọc tham số `token` từ URL query params khi quét mã QR để handshake tức thì, không bị phụ thuộc vào việc fetch token mới.
5. Chạy kiểm thử xác thực:
   - `python -m pytest tests/test_milestone_m2_qr_guest.py -v --basetemp=.pytest_temp_m1` (phải đạt 100% PASS).
   - Kiểm tra Vercel deployment URL và trạng thái kết nối.

Viết báo cáo bàn giao chi tiết (bao gồm lệnh đã chạy, kết quả, file đã sửa, git/vercel URL) vào:
`c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m1\handoff.md`
Khi hoàn tất, gửi tin nhắn báo cáo cho Orchestrator kèm đường dẫn file bàn giao.
