# Bảng Phân Quyền Cố Định 3 Tầng (RBAC — Hợp Đồng Khóa Cứng 6 Thiết Bị)

Bảng phân quyền dưới đây được mã hóa tại nguồn sự thật duy nhất [`backend/auth/tier_permissions.py`](../backend/auth/tier_permissions.py) và được máy chủ kiểm tra bắt buộc cho **mọi** kênh điều khiển (REST API, WebSocket giọng nói AI, Mobile PWA `/app`, ứng dụng Android và trang khách `/guest`). Client tuyệt đối không thể tự nâng quyền.

> **Quy tắc kiểm tra:** Người dùng mang cấp quyền `T` chỉ được điều khiển thiết bị khi `T <= min_tier` của thiết bị đó (số cấp nhỏ hơn tương ứng quyền cao hơn: `1` = Chủ nhà, `2` = Thành viên, `3` = Khách).

---

## 1. Ma Trận Quyền Điều Khiển 6 Thiết Bị Chấp Hành

| Thiết bị chấp hành | Mã định danh (`device_id`) | Chân ESP8266 | Cấp 1 · Chủ nhà (`ADMIN`) | Cấp 2 · Thành viên (`MEMBER`) | Cấp 3 · Khách (`CHILD_GUEST`) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Cửa chính (Servo SG90)** | `main_door` | `D1` (`GPIO5`) | **Có** | Không | Không |
| **Còi báo động (Buzzer 5V)** | `alarm_siren` | `D8` (`GPIO15`) | **Có** | Không | Không |
| **Máy bơm tưới cây (Relay 1)** | `garden_pump` | `D6` (`GPIO12`) | **Có** | **Có** | Không |
| **Loa phản hồi (`PAM8403` · Relay 2)** | `speaker_amp` | `D7` (`GPIO13`) | **Có** | **Có** | Không |
| **Đèn phòng khách (LED 5mm)** | `living_room_light` | `D0` (`GPIO16`) | **Có** | **Có** | **Có** |
| **Đèn phòng ngủ (LED 5mm Active-LOW)** | `bedroom_light` | `D4` (`GPIO2`) | **Có** | **Có** | **Có** |

> **Xác nhận khóa phạm vi:** Hệ thống chỉ có đúng **6 thiết bị chấp hành** nêu trên và **3 cảm biến** (`dht11`, `soil_moisture`, `ky037` — mọi cấp đã đăng nhập đều được xem). Không tồn tại quạt (`fan`), điều hòa (`ac`) hay hồng ngoại (`IR`).

---

## 2. Ma Trận Quyền Trang Giao Diện & Chức Năng Quản Trị

| Chức năng / Tuyến trang | Cấp 1 · Chủ nhà | Cấp 2 · Thành viên | Cấp 3 · Khách |
| :--- | :---: | :---: | :---: |
| Tổng quan 3D (`/`) & Mobile Web (`/app`) | Có (6/6 thiết bị) | Có (4/6 thiết bị) | Có (2/6 thiết bị) |
| Tự động hóa (`/automation`): Luật, lịch, hẹn giờ, lệnh tùy chỉnh | Toàn quyền (toàn nhà) | Bể riêng (4 thiết bị, không đè lịch Cấp 1) | Chỉ xem (ẩn nút tạo/sửa/xóa) |
| Hướng dẫn đấu nối phần cứng (`/wokwi`) | Có | Có | Bị chặn (`HTTP 403`) |
| Nhật ký kiểm toán & SQLite (`/logs`) | Có | Bị chặn (`HTTP 403`) | Bị chặn (`HTTP 403`) |
| Tạo / thu hồi mã mời QR dùng một lần & duyệt thành viên (`/auth`) | Có *(bảo vệ bằng PIN Chủ nhà)* | Không *(trừ khi được cấp cờ `can_create_links` cho Cấp 3)* | Không |
| Khôi phục cài đặt gốc toàn hệ thống (`Reset`) | Toàn nhà | Chỉ xóa bể riêng của mình | Không |

API đọc bảng quyền hiện hành từ máy chủ: `GET /api/auth3/permissions`.

Xem thêm kiến trúc chi tiết xác thực & mã mời QR tại [`docs/kien_truc/KIEN_TRUC_HE_THONG.md`](kien_truc/KIEN_TRUC_HE_THONG.md) và hướng dẫn sử dụng tại [`USER_GUIDE.md`](../USER_GUIDE.md).
