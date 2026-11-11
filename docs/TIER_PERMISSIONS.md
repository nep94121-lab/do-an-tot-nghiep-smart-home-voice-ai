# Bảng quyền cố định theo cấp (Tier 2 / Tier 3)

Bảng này được mã hóa trong `simulator/auth/tier_permissions.py` và được máy chủ áp dụng cho mọi lệnh điều khiển (HTTP, giọng nói, trang khách). Client không được tự nâng quyền. Phiên hợp lệ mới được tạo bằng đăng nhập (email + mật khẩu) hoặc mã mời do chủ nhà phát hành.

Quy tắc: người dùng cấp `T` được điều khiển thiết bị khi `T <= min_tier` của thiết bị (cấp số nhỏ hơn là quyền cao hơn).

| Thiết bị | ID | Cấp 1 · Chủ nhà | Cấp 2 · Gia đình | Cấp 3 · Khách |
|---|---|---|---|---|
| Cửa chính | `main_door` | Có | Không | Không |
| Còi báo động | `alarm_siren` | Có | Không | Không |
| Điều hòa | `ac` | Có | Có | Không |
| Máy bơm tưới cây | `garden_pump` | Có | Có | Không |
| Đèn phòng khách | `living_room_light` | Có | Có | Có |
| Đèn phòng ngủ | `bedroom_light` | Có | Có | Có |
| Quạt trần | `fan` | Có | Có | Có |

- Cấp 1: toàn quyền, tạo/thu hồi mã mời QR (cần PIN 4 số của chủ nhà).
- Cấp 2: đèn, quạt, điều hòa, máy bơm. Không mở cửa chính, không bật còi, không tạo mã mời.
- Cấp 3: chỉ đèn phòng khách, đèn phòng ngủ và quạt trần. Trang khách (`/guest?token=`) chỉ hiện các nút này.

API đọc bảng: `GET /api/auth3/permissions`.
