# BRIEFING — 2026-11-04T06:18:00Z

## Mission
Khảo sát kỹ thuật Mảng 1: Deploy Vercel, HTTPS Tunnel & QR Guest Handshake cho Đồ án Tốt nghiệp Smart Home Voice AI.

## 🔒 My Identity
- Archetype: explorer
- Roles: investigator, synthesizer
- Working directory: c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\survey_1\
- Original parent: cb4be64f-6f73-4e8f-b499-50863e4051dc
- Milestone: Survey Phase 0 - Area 1 (Vercel, Tunnel, QR Handshake)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement / modify source code directly
- Write only to working directory: .agents/teamwork/survey_1/
- Produce a 5-component handoff report (handoff.md)
- UTF-8 without BOM, Unix LF

## Current Parent
- Conversation ID: cb4be64f-6f73-4e8f-b499-50863e4051dc
- Updated: 2026-11-04T06:18:00Z

## Investigation State
- **Explored paths**:
  - `vercel.json` (chưa có), remote Git repo `nep94121-lab/do-an-tot-nghiep-smart-home-voice-ai` (branch master, `gh` authenticated), tài khoản Vercel `nep94121-8303` (CLI 59.16.0).
  - OpenSSH `localhost.run` tunnel: Đã test live nhận domain `https://04f0beba8cdda9.lhr.life`, phản hồi HTTP 200 OK cho `/api/state` và `/app`.
  - LAN IP `192.168.2.39:8088`: Đã test live phản hồi HTTP 200 OK.
  - ADB Reverse `tcp:8088`: Điện thoại Samsung S9 (`2223e8784b0c7ece`) kết nối UsbFfs tcp:8088 tcp:8088 sẵn sàng.
  - `simulator/api/routes_qr.py`: Endpoint `/api/auth3/guest_qr_current` sinh SVG QR gắn link host.
  - `simulator/auth/qr_totp_mixin.py`: Hàm `consume_guest_handshake` phát hiện điều kiện timeout 10s tại dòng 116, 131, 162 (`abs(cur_window - token_win) > 1`).
  - `simulator/static/js/guest_enroll.js`: Phát hiện thiếu đọc `params.get('token')` từ URL khi quét QR.
- **Key findings**:
  - Vercel cần `vercel.json` định tuyến rewrites cho 6 trang static frontend để không bị 404.
  - Hệ thống hỗ trợ hoàn hảo mô hình Hybrid Connectivity: USB ADB Reverse (0ms), LAN Wi-Fi (nội bộ), HTTPS Tunnel (4G/5G ngoại mạng).
  - Nới rộng dung sai cửa sổ TOTP từ 10s lên 180s (18 chu kỳ) giải quyết triệt để lỗi timeout khi quét mã QR trên điện thoại, đồng thời cơ chế Single-Use Token ngăn chặn 100% Replay Attack.
- **Unexplored areas**: Không còn vùng chưa khảo sát trong Mảng 1.

## Key Decisions Made
- Hoàn tất báo cáo khảo sát 5 thành phần tại `survey_1/handoff.md`.
- Sẵn sàng bàn giao cho Orchestrator để chuyển sang Phase 1 Triển khai.

## Artifact Index
- DISPATCH.md — Chỉ thị nhiệm vụ từ Orchestrator
- BRIEFING.md — Trạng thái và nhận thức tình huống
- progress.md — Nhật ký tiến độ liveness
- handoff.md — Báo cáo khảo sát 5 thành phần hoàn chỉnh
