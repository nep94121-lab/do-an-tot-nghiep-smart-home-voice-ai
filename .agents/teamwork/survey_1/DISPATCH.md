## 2026-11-04T06:04:15Z
Bạn là Subagent teamwork_explorer thực hiện nhiệm vụ Khảo sát Kỹ thuật (Survey Phase 0) - Mảng 1: Deploy Vercel, HTTPS Tunnel & QR Guest Handshake.

MANDATORY: Đọc kỹ file yêu cầu gốc của Sếp tại:
`c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md`

Thư mục làm việc của bạn: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\survey_1\`
(Chỉ ghi file báo cáo / metadata trong thư mục này, KHÔNG sửa mã nguồn hệ thống ở bước khảo sát).

Nhiệm vụ cụ thể:
1. Khảo sát cấu hình Deploy Vercel & Git:
   - Kiểm tra `vercel.json` (nếu có), remote Git repo `nep94121-lab/do-an-tot-nghiep-smart-home-voice-ai`, trạng thái git branch, static files, frontend build hoặc routes.
   - Kiểm tra khả năng chạy `vercel --prod --yes` và cách tích hợp frontend/backend.
2. Khảo sát HTTPS Tunnel & LAN & ADB Reverse:
   - Kiểm tra kết nối OpenSSH `localhost.run` (`ssh -o StrictHostKeyChecking=no -R 80:127.0.0.1:8088 nokey@localhost.run`).
   - Kiểm tra cách lấy IP LAN máy chủ (`http://192.168.2.39:8088`) và `adb reverse tcp:8088 tcp:8088`.
   - Kiểm tra cổng FastAPI server đang chạy (8088), router `/api/auth3/guest_qr_current` & `/api/auth3/qr/generate` trong `simulator/api/routes_qr.py`.
3. Khảo sát TOTP Guest Handshake:
   - Đọc và phân tích `simulator/auth/qr_totp_mixin.py` hàm `consume_guest_handshake`.
   - Xác định chính xác vị trí thời gian hết hạn (cửa sổ thời gian hiện tại vs yêu cầu nới rộng để không bị timeout 10s khi quét mã QR trên điện thoại).
4. Lập danh mục Feature, rủi ro, ràng buộc kỹ thuật và đề xuất giải pháp chi tiết.

Viết báo cáo đầy đủ, chi tiết vào:
`c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\survey_1\handoff.md`
Khi hoàn tất, gửi tin nhắn báo cho Orchestrator với đường dẫn file báo cáo.


## 2026-11-04T06:15:44Z
**Context**: [Kiểm tra tiến độ khảo sát Phase 0]
**Content**: Safety timer 10 phút vừa kích hoạt. Xin hỏi tình trạng tiến độ khảo sát của bạn về Deploy Vercel, HTTPS Tunnel & QR Guest Handshake.
**Action**: Hãy báo cáo tiến độ hiện tại hoặc hoàn tất viết file `survey_1/handoff.md` và phản hồi.
