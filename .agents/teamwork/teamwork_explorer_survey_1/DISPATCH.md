## 2026-11-04T19:14:43Z
[Message] sender=4fbd627a-a119-4a5e-84ba-b07fb631efd7 priority=MESSAGE_PRIORITY_HIGH
Role: teamwork_explorer_survey_1
Mission: Investigate and analyze authoritative codebase for Bug 1, Bug 2, Bug 4, Bug 5, Bug 15.
- Bug 1: BẢO MẬT: Modal đăng nhập trên `/` tự mở với email + mật khẩu owner điền sẵn và hiển thị dòng "Mật khẩu mặc định: ******". Xoá mọi credential điền sẵn và mọi gợi ý mật khẩu mặc định khỏi UI (/, /app, /auth). Trong phần HIỂN THỊ của /logs phải che gợi ý mật khẩu (vd "Mật khẩu gợi ý: GiaDinh@12…"). Không bao giờ hiển thị mật khẩu trên UI/log.
- Bug 2: Đăng xuất trên `/`: modal mở lại với mật khẩu cũ + thông báo cũ "Đăng nhập thành công"; header ghi "Chưa đăng nhập" nhưng nút Đăng xuất vẫn hiện. Sau logout phải xoá form, thông báo, session state và ẩn Đăng xuất. Trên /app cũng bị điền sẵn credential sau logout.
- Bug 4: Quên mật khẩu bằng OTP: "Gửi OTP" cho senat6031@gmail.com trả về "Không tìm thấy tài khoản". Đảm bảo tài khoản test senat6031@gmail.com (thành viên gia đình, tier 2) và kbanh376@gmail.com (khách, tier 3) có trong seed trên production (không ghi mật khẩu vào báo cáo). OTP phải gửi mail thật qua cấu hình Gmail/SMTP sẵn có của dự án. Chia bước: nhập email → nhập OTP → đặt mật khẩu mới; ô mật khẩu không được điền sẵn.
- Bug 5: /auth: wizard đăng ký giọng nói có dữ liệu thành viên mẫu điền sẵn; "Kiểm tra đăng nhập" lỗi. Xoá dữ liệu mẫu, làm cho kiểm tra hoạt động với tài khoản thật.
- Bug 15: Header desktop: chưa hiển thị thời gian truy cập còn lại của người đăng nhập. Thêm vào (owner hiện "Không giới hạn").
