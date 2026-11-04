# Original User Request

## Parameters
[skip-interview]
How this run was launched; not part of the task.

## Initial Request — 2026-11-04T06:01:00Z

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


## Follow-up — 2026-11-04T06:06:41Z

THÔNG BÁO CẬP NHẬT QUAN TRỌNG:
Người dùng đã cắm lại cáp USB và chiếc điện thoại **Samsung Galaxy S9 (`2223e8784b0c7ece`, `SM_G960F`)** hiện ĐÃ KẾT NỐI ADB THÀNH CÔNG (`device` state)!
Lưu ý khi gọi ADB trên máy này:
- Luôn đặt biến môi trường `$env:ADB_LIBUSB="1"` (hoặc `os.environ["ADB_LIBUSB"] = "1"` trong Python) trước khi gọi `C:\Users\LENOVO\AppData\Local\Android\Sdk\platform-tools\adb.exe -s 2223e8784b0c7ece ...`
- Đã bật `adb -s 2223e8784b0c7ece reverse tcp:8088 tcp:8088`.
- Yêu cầu bắt buộc của người dùng: Khi test trên điện thoại qua ADB (đăng nhập, quét/mở QR mời khách, bật tắt thiết bị đồng bộ với Web), **MỖI BƯỚC ĐỀU PHẢI CHỤP ẢNH MÀN HÌNH (`screencap -p`) VÀ TỰ ĐỌC LẠI ẢNH (`read_file`) ĐỂ KIỂM TRA XEM ĐÚNG LUỒNG CHƯA, NẾU CHƯA ĐÚNG PHẢI TỰ SỬA NGAY**.
