# REAL_TEST_BUGS_20261105 — Lỗi phát hiện khi test thực tế trên production (05/11/2026)

1. BẢO MẬT: Modal đăng nhập trên `/` tự mở với email + mật khẩu owner điền sẵn và hiển thị dòng "Mật khẩu mặc định: ******". Xoá mọi credential điền sẵn và mọi gợi ý mật khẩu mặc định khỏi UI (/, /app, /auth). Trong phần HIỂN THỊ của /logs phải che gợi ý mật khẩu (vd "Mật khẩu gợi ý: GiaDinh@12…"). Không bao giờ hiển thị mật khẩu trên UI/log.
2. Đăng xuất trên `/`: modal mở lại với mật khẩu cũ + thông báo cũ "Đăng nhập thành công"; header ghi "Chưa đăng nhập" nhưng nút Đăng xuất vẫn hiện. Sau logout phải xoá form, thông báo, session state và ẩn Đăng xuất. Trên /app cũng bị điền sẵn credential sau logout.
3. WebSocket trên Vercel production lỗi (`wss://.../ws`); dashboard hiện banner "Mất kết nối thời gian thực" trong khi header ghi "Đã kết nối". Vercel serverless không giữ WebSocket → thêm fallback tự động sang HTTP polling /api/state; khi polling hoạt động không hiện banner đỏ/vàng. Banner và trạng thái header phải nhất quán, đúng sự thật. Sửa resource 404 trong console.
4. Quên mật khẩu bằng OTP: "Gửi OTP" cho senat6031@gmail.com trả về "Không tìm thấy tài khoản". Đảm bảo tài khoản test senat6031@gmail.com (thành viên gia đình, tier 2) và kbanh376@gmail.com (khách, tier 3) có trong seed trên production (không ghi mật khẩu vào báo cáo). OTP phải gửi mail thật qua cấu hình Gmail/SMTP sẵn có của dự án. Chia bước: nhập email → nhập OTP → đặt mật khẩu mới; ô mật khẩu không được điền sẵn.
5. /auth: wizard đăng ký giọng nói có dữ liệu thành viên mẫu điền sẵn; "Kiểm tra đăng nhập" lỗi. Xoá dữ liệu mẫu, làm cho kiểm tra hoạt động với tài khoản thật.
6. /app 3D thu gọn chỉ hiện placeholder nét đứt "Mô hình Toàn cảnh 3D", không render. Render house3d thu gọn thật (giữ concept, chỉ Toàn cảnh).
7. Tab Thiết bị /app chỉ có 4 thiết bị (cửa, 2 đèn, quạt); thiếu điều hoà, còi, bơm — phải đủ 7 như desktop.
8. Tab Hồ sơ /app: nút "Đăng xuất" bị bottom nav che (cần padding/safe-area, kể cả toolbar Samsung Internet). Xoá dòng "Mỗi tab mở một màn riêng...". Hàng "Mời khách" hiện đếm ngược "Còn Ns" nhảy liên tục như giá trị list → làm rõ ràng hơn.
9. Desktop `/`: không có panel cảm biến nhiệt độ/độ ẩm/độ ẩm đất. Thêm panel cảm biến gọn; giá trị được clamp, hợp lý.
10. Bật/tắt đèn chậm; trong lúc cập nhật nhãn bị trống và phụ đề bị cắt thành "Đã bột". Dùng optimistic UI, không nhãn trống, chữ đầy đủ.
11. Sheet ghi âm hiện "Đang thu âm" khi popup xin quyền mic còn chờ. Phải có trạng thái "đang chờ quyền mic", chỉ chạy timer/waveform sau khi được cấp quyền; bị từ chối thì hiện modal quyền mic.
12. QR scanner: dòng "Đưa mã QR vào trong khung để quét" hiện 2 lần → bỏ bản trùng.
13. /logs render ~300 dòng trên một trang dài → thêm phân trang hoặc nút "xem thêm" + bộ lọc.
14. /wokwi: nhãn mạch bị cắt/chồng (vd "Cảm biến DHT11 (Chân D…"), trang hiện "Chưa có dữ liệu". Sửa layout nhãn và hiển thị dữ liệu mô phỏng.
15. Header desktop: chưa hiển thị thời gian truy cập còn lại của người đăng nhập. Thêm vào (owner hiện "Không giới hạn").
