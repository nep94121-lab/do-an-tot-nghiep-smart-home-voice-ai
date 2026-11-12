# Phiên đăng nhập, mã mời và quyền cố định

Quyền luôn lấy từ phiên server đã xác thực. JSON `role`, `tier`, `user_id`, trạng thái
`set_active_user` và dữ liệu localStorage không cấp quyền. Không có phiên hợp lệ:
POST `/api/device` (kể cả các alias), `/api/text_command`, `/api/session/role` trả 401.
`/api/session/role` chỉ đọc vai trò phiên hiện tại, không tạo cookie hoặc nâng cấp quyền.

| Chức năng | Chủ nhà cấp 1 | Khách/thành viên cấp 2 | Khách cấp 3 |
|---|---|---|---|
| Đèn phòng khách, đèn phòng ngủ, quạt | Có | Có | Có |
| Điều hòa, máy bơm | Có | Có | Không |
| Cửa/khóa chính, còi báo động | Có | Không | Không |
| Hẹn giờ thiết bị được phép | Có | Có | Không |
| Cài đặt, chế độ server, ghi dữ liệu cảm biến, học IR | Có | Không | Không |
| Quản lý người dùng, cấp/thu hồi quyền | Có | Không | Không |
| Tạo/xem/thu hồi mã mời, quản lý PIN | Có | Không | Không |
| Sửa luật, alias, chính sách qua WebSocket/Gemini | Có | Không | Không |

Nguồn bảng thiết bị: `simulator/auth/tier_permissions.py`. Các đường REST, WebSocket,
lệnh nói và chế độ offline kiểm tra quyền ở server. Giao diện `/guest?token=…` chỉ
hiện các thiết bị trong bảng; không có menu quản trị. Mã sai/hết hạn không mở trang khách.
Route Vercel chuyển trang khách qua backend để kiểm tra token thay vì trang thu giọng cũ.

## Đăng ký và đăng nhập

- Đăng ký bằng Gmail và mật khẩu, xác nhận mật khẩu; tên là tùy chọn. Không thu giọng.
- Đăng ký mới không có mã mời tạo tài khoản chờ chủ nhà cấp quyền, không cấp phiên điều khiển.
- Mã mời hợp lệ chỉ cấp 2 hoặc 3. Quyền và thời hạn của phiên gắn với mã mời;
  đăng nhập lại không kéo dài mã mời. Thu hồi/hết hạn được kiểm tra lại trên từng hành động.
- Endpoint đăng ký không được đổi mật khẩu tài khoản đã có. Dùng luồng khôi phục OTP.
- Đăng nhập không chấp nhận `login_method` tự khai để bỏ qua mật khẩu.
- Các route mời/thu giọng cũ không còn cấp quyền (410). QR alias dùng chung luồng PIN.
- Token fixture dự đoán được chỉ tồn tại trong pytest; server thật từ chối cả bản đã lưu.
- Chữ ký phiên dùng secret triển khai (`SMARTHOME_SESSION_SECRET`, hoặc secret Gmail/SMTP
  có sẵn), không dùng hash mật khẩu có trong repository. Phiên kiểu cũ cần đăng nhập lại.

## PIN và Quên PIN

Chủ nhà đăng nhập, nhập PIN 4 chữ số hai lần ở lần đầu. Server lưu PBKDF2-SHA256 với
salt ngẫu nhiên, không lưu PIN thô. Sai 5 lần khóa tạo mã mời; nhập đúng cũng không mở
khóa, phải đặt lại qua Gmail. Tạo QR dùng POST; GET không tạo mã hoặc gửi PIN qua URL.

Quên PIN chỉ gửi tới `nep94121@gmail.com`. Mã 6 số lưu hash, hết hạn sau 5 phút,
dùng một lần; sai 5 lần khóa mã, gửi lại có thời gian chờ 60 giây. Production không
trả mã OTP trong HTTP. Email lỗi không được thông báo là gửi thành công.

PIN và danh sách mã mời nằm trong repository GitHub private riêng. Mỗi lần cập nhật
đọc SHA của tài liệu rồi ghi có điều kiện với SHA đó. Xung đột sẽ đọc lại và tính lại
toàn bộ thao tác. OTP chỉ gửi mail sau khi giao dịch phát mã đã thành công. Tạo phiên
khách diễn ra sau khi ghi lượt đổi mã thành công.

Production dùng `SMARTHOME_SECURITY_REPO` và `SMARTHOME_SECURITY_TOKEN` lưu dưới dạng
Secret trong Vercel. Repository phải private. Tài liệu bị thiếu, kho lỗi hoặc hết giới
hạn API trả 503. Không rơi về cache, KV hoặc Gmail cũ. Không xóa tài khoản hoặc lịch sử invite.

## Giới hạn cần biết

Kho GitHub private dùng giới hạn API miễn phí của tài khoản. Hết giới hạn sẽ tạm từ
chối thao tác bảo mật thay vì dùng bản dữ liệu cũ. Token triển khai cần quyền Contents
đọc và ghi repository trạng thái. Nên thay bằng token giới hạn riêng repository này
khi có thể. Không đưa token vào mã hoặc log.

Kho tài khoản JSON cũ vẫn là thành phần riêng. Khóa đăng ký chống trùng email trong
một process, chưa bảo đảm tính duy nhất email giữa nhiều instance. ID mới ngẫu nhiên
và chỉ email chủ nhà chính xác có thể nhận ADMIN, nên việc trùng ID từ email không
còn cấp quyền root. Lỗi lưu hoặc tạo phiên giữ tài khoản chưa kích hoạt và không cấp cookie.

Hợp đồng cập nhật có SHA và lỗi 409 được mô tả trong
[GitHub Contents API](https://docs.github.com/en/rest/repos/contents).
