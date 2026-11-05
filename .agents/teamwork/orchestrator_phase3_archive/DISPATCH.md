# Dispatch Log

## 2026-11-04T06:02:21Z
You are the Project Orchestrator for this task.
Working directory: c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\orchestrator\
Original request file: c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md

Request (verbatim):
<<<REQUEST
Bạn làm việc mà làm đi chứ. Vấn đề hiện tại là chúng ta cần phải deploy hết lên Vercel, rồi chúng ta cần phải deploy lên để test được mấy cái như đăng nhập, test được cái mời, rồi test được cả thao tác trên điện thoại để kích hoạt bật tắt cái ở trên web. Và khi dùng ADB với cả điện thoại, mỗi bước bạn làm đều phải chụp ảnh một bước để xem có đúng luồng không. Chụp xong thì phải tự xem lại xem nó đúng chưa, chưa đúng phải tự sửa. Hiện tại tôi thấy là nó vẫn chưa hoàn thiện được các bước cũ đâu bởi vì Cloudflare nó hết quota nên là chúng ta phải làm rồi kiểm tra nhanh và hỏi tôi vài cái xác nhận rồi vào làm. Quan trọng đó chính là không được gian lận và không được ảo tưởng. Chúng ta có những bài test rồi đấy, có bài test xong rồi, có bài test chưa xong đâu, nhất là mấy bài về giọng nói của tôi.

---
### BỐI CẢNH ĐÃ PHỎNG VẤN & XÁC NHẬN VỚI NGƯỜI DÙNG (GRILL-ME DECISIONS):
1. **Phương án Deploy Vercel & Kết nối Điện thoại / Mã QR (A1):**
   - Deploy lên Vercel (`vercel --prod --yes` theo skill `deploy-github-vercel`, repo GitHub `nep94121-lab/do-an-tot-nghiep-smart-home-voice-ai`) kết hợp HTTPS Tunnel (`OpenSSH localhost.run`: `ssh -o StrictHostKeyChecking=no -R 80:127.0.0.1:8088 nokey@localhost.run`) + IP LAN (`http://192.168.2.39:8088`) + ADB Reverse (`adb reverse tcp:8088 tcp:8088`) nối trực tiếp vào FastAPI Server đang chạy trên máy (`localhost:8088`), tự động gắn link public/LAN vào Mã QR (`/api/auth3/guest_qr_current` & `/api/auth3/qr/generate` trong `simulator/api/routes_qr.py`).
   - Nới rộng cửa sổ thời gian trong `consume_guest_handshake` (`simulator/auth/qr_totp_mixin.py`) để khi quét mã QR trên điện thoại không bị báo hết hạn 10s giữa chừng.

2. **Cổng Đăng nhập (Login Gate) & Ô nhập Mật khẩu (A2):**
   - Khóa cứng Login Gate (`#homeLoginGateModal` trong `simulator/static/index.html` & `simulator/static/js/app.js`): Bỏ/ẩn hoàn toàn nút `X` (`#btnCloseLoginGateModal`) khi chưa đăng nhập để không ai bấm X tắt bỏ qua được! Bắt buộc đăng nhập bằng Email (`nep94121@gmail.com`) + Mật khẩu (`123456`).
   - Mở khóa mọi ô input (bỏ `readOnly = true` trong `simulator/static/js/auth.js` dòng 56, 60) để người dùng bấm sửa tự do; bọc `<form>` hỗ trợ nhấn phím Enter; thêm nút 👁️ Hiện/Ẩn mật khẩu; bắt buộc 2 ô xác nhận mật khẩu khi tạo/đổi mật khẩu trên cả Web và Mobile (`/app`).
   - Sửa lỗi trong `mobile_app/index.html`: Đưa khối `<svg>` chứa `<symbol id="i-home">...` ra ngoài `<div id="mobileMainContent" hidden>` để icon hiển thị đúng trên `#mobileLoginGate`.

3. **Sửa lỗi Giao diện Nút bấm trên Mô hình 3D (`simulator/static/house3d.js`, `simulator/static/index.html`, `simulator/static/css/style.css`):**
   - Trong `simulator/static/house3d.js` dòng 179: `container.innerHTML = ""` đang xóa mất `#house3dLabels` và `.viewport-note` nằm bên trong `#house3dViewport`! Phải sửa thành chỉ xóa `<canvas>` cũ (nếu có) và `container.insertBefore(renderer.domElement, container.firstChild)` để giữ nguyên `#house3dLabels` nổi trên mô hình 3D!
   - Bỏ `.pin-3d .pin-icon { display: none !important; }` trong `simulator/static/css/style.css` để các nút nổi `.pin-3d` trên 7 thiết bị 3D hiển thị rõ icon + tên + trạng thái BẬT/TẮT và bấm vào bật/tắt trực tiếp thiết bị.
   - Thêm thanh nút chọn góc nhìn Camera 3D (`Toàn cảnh`, `Phòng khách`, `Phòng ngủ`, `Cửa chính`, `Sân vườn`, `Mạch ESP`, `Tự xoay`) trên header của panel Ngôi nhà 3D trong `index.html`.
   - Thêm `THREE.Raycaster` khi click vào mô hình 3D để bật/tắt thiết bị.

4. **Kiểm thử Giọng nói thật của Sếp & Chụp ảnh màn hình Web + Điện thoại (ADB) từng bước (A3 & A4):**
   - Dùng các file âm thanh giọng nói thật của Sếp Nguyễn Tuấn Anh (`test_audio/giong_chu_nha_cap1_tuan_anh.wav` và các câu lệnh đã cắt trong `test_audio/cac_cau_lenh_cua_sep/`) chạy kiểm thử thực tế qua Voice Auth + STT + Rule Engine + WebSocket để mở/đóng cửa chính, bật/tắt đèn phòng khách, đèn phòng ngủ, quạt trần, điều hòa.
   - Chụp ảnh màn hình từng bước (Web qua trình duyệt & Điện thoại qua ADB `C:\Users\LENOVO\AppData\Local\Android\Sdk\platform-tools\adb.exe` với `ADB_LIBUSB=1`, serial `2223e8784b0c7ece` hoặc IP `192.168.2.142`), tự đọc lại từng ảnh chụp bằng `read_file` để kiểm chứng mắt thường xem giao diện và trạng thái đã đúng 100% chưa, nếu sai phải tự sửa ngay.
   - Chạy toàn bộ pytest (`--basetemp` riêng để tránh lỗi lock thư mục tạm Windows) và `tests/test_challenger_m4_dom.py` đạt 100% PASS.
REQUEST>>>


## 2026-11-04T06:07:06Z
[Follow-up from User / Caller]:
THÔNG BÁO CẬP NHẬT QUAN TRỌNG:
Người dùng đã cắm lại cáp USB và chiếc điện thoại **Samsung Galaxy S9 (`2223e8784b0c7ece`, `SM_G960F`)** hiện ĐÃ KẾT NỐI ADB THÀNH CÔNG (`device` state)!
Lưu ý khi gọi ADB trên máy này:
- Luôn đặt biến môi trường `$env:ADB_LIBUSB="1"` (hoặc `os.environ["ADB_LIBUSB"] = "1"` trong Python) trước khi gọi `C:\Users\LENOVO\AppData\Local\Android\Sdk\platform-tools\adb.exe -s 2223e8784b0c7ece ...`
- Đã bật `adb -s 2223e8784b0c7ece reverse tcp:8088 tcp:8088`.
- Yêu cầu bắt buộc của người dùng: Khi test trên điện thoại qua ADB (đăng nhập, quét/mở QR mời khách, bật tắt thiết bị đồng bộ với Web), **MỖI BƯỚC ĐỀU PHẢI CHỤP ẢNH MÀN HÌNH (`screencap -p`) VÀ TỰ ĐỌC LẠI ẢNH (`read_file`) ĐỂ KIỂM TRA XEM ĐÚNG LUỒNG CHƯA, NẾU CHƯA ĐÚNG PHẢI TỰ SỬA NGAY**.


## 2026-11-04T15:01:30Z
Triển khai Giai đoạn 3 (Phase 3) cho đồ án tốt nghiệp: sửa lỗi routing Vercel production, chuyển RBAC sang quản lý theo từng session/request, kiểm tra và build Android native Compose (M1–M5), refactor mô-đun hóa toàn dự án theo nguyên tắc skill ponytail, vượt qua toàn bộ gating kiểm thử và deploy Vercel production.

Working directory: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp
Integrity mode: development

## Reference Material
- FIX_REPORT_20261104.md
- FIX_PLAN_20261104.md
- UI Mockups: ui_mockups/v2_new_pages (np_m1..np_m5)
- Production Domain: https://do-an-tot-nghiep-smart-home-voice-a.vercel.app

## Requirements

### R1. Sửa routing Vercel production
Sửa lỗi routing trên https://do-an-tot-nghiep-smart-home-voice-a.vercel.app: các đường dẫn /mobile, /architecture, /offline, /404, /403, /500, /qr_expired, /sw.js phải hoạt động và không trả về Vercel NOT_FOUND. URL không tồn tại phải hiện trang 404 tùy biến. /mobile chuyển hướng về /app nếu đó là trang dự định. Sau deploy phải kiểm tra bằng curl trên production domain thật (...voice-a.vercel.app).

### R2. Bảo mật RBAC theo session
Đổi tier RBAC từ lấy state global của engine (user đăng nhập cuối) sang quản lý theo từng session (cookie/token) cho mỗi request để 2 người dùng đồng thời không bao giờ lẫn quyền. Bổ sung test kiểm thử cho các session đồng thời của 3 vai trò (owner, admin, user/guest).

### R3. Android native Compose
Kiểm tra các màn M1–M5 đúng theo ui_mockups/v2_new_pages (np_m1..np_m5). Lệnh assembleDebug phải hoàn thành với kết quả SUCCESSFUL. Nếu thiết bị S9 (adb serial 2223e8784b0c7ece, adb tại %LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe) đang kết nối thì cài APK, mở app, lưu screencap vào ui_mockups/android_phase3/.

### R4. Quét dự án và refactor mô-đun hóa
Tải/cài skill ponytail (tìm qua agy plugin/skills, GitHub...; cài nếu tìm thấy). Dùng skill này hoặc tuân theo nguyên tắc của nó để quét toàn dự án và refactor: tách các file dài hàng nghìn dòng (app.js, các module Python, MainScreen.kt...) thành module rõ ràng, xóa dead code và code trùng lặp, sắp xếp thư mục gọn gàng. Tuyệt đối KHÔNG thay đổi hành vi. Giữ concept 3D house3d.js và thiết kế v1 sáng. Không xóa file thiết kế trong ui_mockups. Giữ đầy đủ các re-export/entry-point/DOM IDs/window hooks mà các bài test E2E và Challenger đang kiểm tra.

### R5. Verification Gates
Toàn bộ pytest PASS 100% (chạy với python -X utf8 -m pytest tests/ --basetemp=.pytest_tmp và xóa .pytest_tmp sau khi chạy). Playwright/luồng thật cho 3 vai trò PASS. assembleDebug SUCCESSFUL. Reviewer xác nhận không đổi hành vi; auditor xác nhận không có facade hay test gian lận. Không dừng khi còn bất kỳ FAIL nào. Dùng mật khẩu mặc định của tài khoản owner trong seed của dự án (không ghi vào báo cáo).

### R6. Git Commit, Vercel Deploy và Báo cáo
Chỉ làm trong thư mục dự án, không đụng Desktop BA-SVD hay vị trí khác ngoài dự án. Commit, push lên master, deploy Vercel production, kiểm tra lại mọi URL production. Thêm mục Phase 3 vào FIX_REPORT_20261104.md với số dòng trước/sau của các file lớn.

## 2026-11-04T17:03:48Z
[Server Restart Recovery & User Follow-up Notification]:
Hệ thống vừa phục hồi sau server restart. Hãy tiếp tục trực tiếp từ trạng thái hiện tại (M11, M12, M13 đã Gate PASS; M14 Worker đã hoàn tất phân rã dead code, voice_auth, MainScreen.kt và assembleDebug SUCCESSFUL). Tiếp tục chốt Gate M14 và tiến hành M15.

Chỉ thị bổ sung quan trọng từ Người dùng:
Lưu ý bổ sung từ người dùng (đảm bảo bao phủ 100% cả Phase 2 và Phase 3 trong cổng nghiệm thu M15 đang chạy, không khởi tạo lại từ đầu để tránh xung đột với M14/M15 đang hoàn tất):
- Giữ nguyên toàn bộ tiến độ Phase 3 hiện tại (M11, M12, M13 đã Gate PASS; M14 Worker đã hoàn tất `-1,989L` dead code, `-1,111L` `voice_auth.py`, `-1,860L` `MainScreen.kt`, `assembleDebug SUCCESSFUL` và đang chốt Gate M14 để sang M15).
- Trong bước M15 (Full Gate, Deploy & Report), đảm bảo kiểm tra gộp toàn bộ tiêu chí của cả Phase 2 (`DESIGN_NEW_PAGES.md`: `offline`+`sw.js`, `404`, `500/503`, `QR expired`, `403`, `lockdown modal`, `mic permission`, `WS reconnect banner`, 5 màn mobile `M1`–`M5`, Android Compose `assembleDebug`, test luồng thật 3 vai Chủ nhà `nep94121@gmail.com` / Gia đình / Khách trên `http://localhost:8088`, toàn bộ `pytest` PASS 100%) cùng toàn bộ tiêu chí của Phase 3 (Vercel routing trên `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`, Session-based RBAC, Ponytail refactor, `FIX_REPORT_20261104.md` gộp đủ Phase 1 + Phase 2 + Phase 3, commit + push `master` + deploy Vercel production).

