# Báo Cáo Bàn Giao Kỹ Thuật (Milestone 1)
## Deployment & Connectivity (Vercel, HTTPS Tunnel, LAN IP & QR TOTP Extension)

**Người thực hiện:** `worker_m1` (Teamwork Implementer & QA)  
**Ngày thực hiện:** 2026-11-04  
**Chỉ thị dispatch:** `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m1\DISPATCH.md`  
**Quyền sở hữu tệp (Write Ownership):**
1. `vercel.json` (tạo mới ở thư mục gốc)
2. `simulator/auth/qr_totp_mixin.py`
3. `simulator/api/routes_qr.py`
4. `simulator/static/js/guest_enroll.js`

---

## 1. Observation (Dữ Liệu & Thực Nghiệm Trực Tiếp)

### 1.1. Hiện trạng Mã nguồn Trước khi Sửa
- Trong `simulator/auth/qr_totp_mixin.py` (dòng 131 và 162):
  - Vòng lặp HMAC fallback chỉ kiểm tra: `for w_chk in (cur_window, cur_window - 1):` (tối đa lùi 1 chu kỳ = 10s).
  - Điều kiện hết hạn: `if abs(cur_window - token_win) > 1: return {"ok": False, "error": "Mã QR đã hết hạn 10 giây...", "status_code": 401}`.
  - Hậu quả: Khi khách quét mã QR trên điện thoại (mất 15 - 45s để mở camera, bấm link, tải trang), request handshake luôn bị máy chủ từ chối với mã 401.
- Trong `simulator/api/routes_qr.py` (dòng 108-113):
  - Logic gán prefix: Nếu `chosen_host` không có `http://` hay `https://`, code mặc định gán `http://{chosen_host}`.
  - Hậu quả: Domain tunnel công cộng như `04f0beba8cdda9.lhr.life` bị gắn nhầm thành `http://` khiến trình duyệt chặn truy cập Microphone (do thiếu Secure Context).
- Trong `simulator/static/js/guest_enroll.js` (dòng 127-143):
  - `initQrHandshake()` chỉ đọc `dur` và `tier`, không đọc tham số `token` và `window` từ URL query params. Nó tự động gọi `refreshGuestQrNow()` để fetch token mới từ server, gây lệch pha với mã QR hiển thị trên màn hình.
- File cấu hình `vercel.json`: Chưa tồn tại ở thư mục gốc.

### 1.2. Các Lệnh Đã Thực Thi & Kết Quả
1. **Kiểm thử Pytest:**
   - Lệnh: `python -m pytest tests/test_milestone_m2_qr_guest.py -v --basetemp=.pytest_temp_m1`
   - Kết quả: `17 passed, 3 warnings in 9.38s` (Đạt 100% PASS, Exit Code: 0).
2. **Kiểm thử Trực Giao Độc Lập (Orthogonal Verification Script):**
   - Lệnh: Kiểm tra sinh token cách 120s (12 chu kỳ), gọi `consume_guest_handshake` -> `res['ok'] is True`.
   - Kiểm tra Single-Use Token replay: Gọi lại token vừa dùng -> `res['ok'] is False` (bảo vệ chống Replay Attack thành công).
   - Kiểm tra token hết hạn > 180s (200s, 20 chu kỳ) -> `res['ok'] is False` (từ chối chính xác).
   - Kiểm tra auto-prefix HTTPS: Gọi `/api/auth3/guest_qr_current?host=04f0beba8cdda9.lhr.life` -> `full_url` bắt đầu bằng `https://04f0beba8cdda9.lhr.life`.
   - Kết quả: `ALL ORTHOGONAL CHECKS PASSED 100%!`.
3. **Triển khai Vercel Production:**
   - Lệnh: `vercel --prod --yes`
   - Vercel Production URL (Aliased): `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`
   - Deployment URL: `https://do-an-tot-nghiep-smart-home-voice-nxjpv0jy8.vercel.app`
   - Inspect Dashboard: `https://vercel.com/tuananhs-projects-8aea56ce/do-an-tot-nghiep-smart-home-voice-ai/7u5m3Wd7mkPhJp4JtHFzgdnepjEk`
   - Kiểm tra phản hồi HTTP thực tế qua Python urllib:
     - `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/` -> `200 OK` (21,418 bytes)
     - `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/app` -> `200 OK` (24,269 bytes)
     - `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/auth` -> `200 OK` (26,896 bytes)
     - `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/guest_enroll` -> `200 OK` (9,806 bytes)
     - `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/logs` -> `200 OK` (13,061 bytes)
     - `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/wokwi` -> `200 OK` (43,616 bytes)
     - `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/archify` -> `200 OK` (862,456 bytes)
     - `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/archify/devops` -> `200 OK` (851,022 bytes)
     - `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/static/style.css` -> `200 OK` (15,817 bytes)
4. **Git Commit & Push:**
   - Lệnh: `git commit -m "feat(milestone1): deploy vercel config, qr totp 180s window, routes_qr https detection and guest enroll token handshake" && git push origin master`
   - Commit Hash: `5d99581`
   - Repository: `https://github.com/nep94121-lab/do-an-tot-nghiep-smart-home-voice-ai.git`

---

## 2. Logic Chain (Chuỗi Lập Luận Kỹ Thuật)

1. **Về Cấu hình Vercel (`vercel.json`):**
   - Dự án là một ứng dụng Hybrid: Backend FastAPI (chứa SQLite WAL, WebSocket hai chiều, mô hình AI âm học) chạy tại máy trạm, trong khi Frontend là tập hợp các trang Web HTML5/CSS3/Three.js phục vụ người dùng.
   - Khi deploy lên Vercel, Vercel tự động nhận diện mã nguồn Python và cố gắng build FastAPI serverless, dẫn đến lỗi "No FastAPI entrypoint found" do các file tham khảo trong `docs/tai_lieu_tham_khao/`.
   - Bằng cách cấu hình `"framework": null`, `"cleanUrls": false` và khai báo bản đồ `routes` chính xác với regex `^/.../?$`, Vercel hoạt động chuẩn xác như một Static Web Showcase, phục vụ đầy đủ 6 trang HTML chính, tài nguyên tĩnh `/static/`, audio `/test_audio/` và hồ sơ kiến trúc `/archify`.
2. **Về Nới Rộng Cửa Sổ Thời Gian Handshake 180s (`qr_totp_mixin.py`):**
   - Vòng quay 10 giây trên giao diện người dùng giúp hiển thị thanh đếm lùi trực quan và chống chụp lén mã QR từ xa.
   - Tuy nhiên, tại tầng backend, việc chấp nhận token được nới rộng lên 18 chu kỳ (180 giây = 3 phút). Cả thuật toán HMAC fallback (`range(cur_window + 2, cur_window - 19, -1)`) và điều kiện chặn (`(cur_window - token_win) > 18 or (token_win - cur_window) > 2`) đều được đồng bộ hóa lên 180s.
   - An toàn thông tin được bảo vệ tuyệt đối nhờ cơ chế **Single-Use Token** (`store.add(clean_tok)`): Dù token có hạn chấp nhận 180s, ngay khi khách bắt tay thành công 1 lần, token lập tức bị vô hiệu hóa. Kẻ xấu replay request sẽ bị máy chủ chặn ngay lập tức với lỗi HTTP 400.
3. **Về Tự Động Nhận Diện HTTPS Tunnel (`routes_qr.py`):**
   - Kiểm tra các chuỗi domain tunnel đặc trưng (`.lhr.life`, `.vercel.app`, `trycloudflare.com`, `.ngrok`, `.loca.lt`) hoặc cổng 443; nếu người dùng nhập host không có scheme, hệ thống tự động gán tiền tố `https://`. Đảm bảo mã QR luôn dẫn đến liên kết Secure Context, cho phép điện thoại cấp quyền Microphone.
4. **Về Handshake Tức Thì Tại Frontend (`guest_enroll.js`):**
   - Bổ sung việc trích xuất `urlToken` và `urlWindow` từ `window.location.search`.
   - Nếu phát hiện trang được mở qua quét mã QR (có `urlToken`), giao diện lập tức thực thi `doGuestHandshake(urlToken, dur, urlWindow)` mà không cần chờ fetch token mới, thiết lập ngay phiên đăng ký và mở quyền thu âm cho khách.

---

## 3. Caveats (Giới Hạn & Lưu Ý)

1. **Phụ thuộc Phiên Tunnel SSH:**
   - Miền công cộng miễn phí từ `localhost.run` (`*.lhr.life`) sẽ thay đổi tên miền con nếu phiên kết nối SSH bị ngắt và tạo lại. Khi đó, người dùng chỉ cần truyền host mới vào tham số `host=` của API tạo mã QR hoặc cấu hình trên UI.
2. **Quyền hạn Tệp:**
   - Subagent `worker_m1` tuân thủ nghiêm ngặt ranh giới phân quyền: Chỉ tạo/chỉnh sửa đúng 4 file được cấp phép (`vercel.json`, `simulator/auth/qr_totp_mixin.py`, `simulator/api/routes_qr.py`, `simulator/static/js/guest_enroll.js`). Toàn bộ các file khác được bảo toàn nguyên vẹn.

---

## 4. Conclusion (Kết Luận Bàn Giao)

- **Milestone 1 ĐÃ HOÀN THÀNH 100%**, đáp ứng toàn bộ các tiêu chí:
  - Vercel Production Deployment: `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app` (Hoạt động ổn định, 100% routes 200 OK).
  - GitHub Remote Repo: `nep94121-lab/do-an-tot-nghiep-smart-home-voice-ai` đã cập nhật commit `5d99581`.
  - TOTP Guest Handshake: Đã nới rộng thành công lên 180s (18 chu kỳ), bảo vệ Single-Use Token hoạt động chuẩn xác chống Replay Attack.
  - Tự động nhận diện HTTPS Tunnel: Hoạt động trơn tru với các tên miền tunnel.
  - Đồng bộ Frontend `guest_enroll.js`: Bắt tay tức thì ngay khi mở trang bằng liên kết QR.
  - Bộ kiểm thử `tests/test_milestone_m2_qr_guest.py` đạt **17/17 PASSED (100%)**.

---

## 5. Verification Method (Hướng Dẫn Kiểm Chứng Độc Lập)

Bất kỳ kiểm định viên hoặc auditor nào đều có thể kiểm chứng lại toàn bộ kết quả bằng các lệnh sau:

1. **Kiểm tra Pytest M2 QR Guest:**
   ```bash
   python -m pytest tests/test_milestone_m2_qr_guest.py -v --basetemp=.pytest_temp_audit
   ```
   *Tiêu chí đạt:* 17/17 tests PASSED, Exit Code: 0.

2. **Kiểm tra Các Endpoints Trên Vercel Production:**
   ```powershell
   python -c "import urllib.request; [print(u, urllib.request.urlopen(u).status) for u in ['https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/', 'https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/app', 'https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/auth', 'https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/guest_enroll', 'https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/logs', 'https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/wokwi', 'https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/archify']]"
   ```
   *Tiêu chí đạt:* Toàn bộ các URL đều trả về mã HTTP `200`.

3. **Kiểm tra Handshake 180s & Single-Use Replay Protection:**
   ```powershell
   python -c "import time, hmac, hashlib; from simulator.auth_3layer import get_auth_3layer_manager; mgr = get_auth_3layer_manager(); cur_w = int(time.time() // 10); past_w = cur_w - 12; tok = hmac.new(b'bk_smarthome_totp_salt_2026', f'{past_w}:1:1d:86400'.encode(), hashlib.sha256).hexdigest()[:16]; res1 = mgr.consume_guest_handshake(tok); assert res1['ok'] is True; res2 = mgr.consume_guest_handshake(tok); assert res2['ok'] is False; print('VERIFICATION_SUCCESS')"
   ```
   *Tiêu chí đạt:* In ra `VERIFICATION_SUCCESS`.
