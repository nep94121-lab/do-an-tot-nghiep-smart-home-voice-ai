# Hướng Dẫn Vận Hành, Kiểm Thử & Triển Khai (`VAN_HANH_VA_TRIEN_KHAI.md`)

Tài liệu này hướng dẫn đầy đủ quy trình vận hành máy chủ cục bộ cổng `8088`, mở truy cập HTTPS qua **Tailscale Funnel** & **Vercel**, sao lưu/phục hồi cơ sở dữ liệu SQLite WAL, khóa triển khai an toàn (`DEPLOY.lock`), và chạy kiểm thử tự động (`pytest`, Playwright headless, Android APK).

> **Nguyên tắc bảo mật:** Không bao giờ đưa tệp `.env`, mật khẩu Wi-Fi, `GEMINI_API_KEY`, `GMAIL_APP_PASSWORD`, `SMARTHOME_SESSION_SECRET`, hay bất kỳ khóa bí mật nào vào Git hoặc tài liệu. Các mục dưới đây **chỉ liệt kê tên biến môi trường**.

---

## 1. Cấu Hình Biến Môi Trường (`.env`)

Tạo tệp `.env` tại thư mục gốc dự án (đã được chặn trong `.gitignore`). Chỉ cần điền các biến phù hợp với môi trường vận hành:

| Tên biến môi trường | Bắt buộc | Vai trò |
| :--- | :---: | :--- |
| `GEMINI_API_KEY` | Có *(cho Voice AI)* | Khóa API gọi Gemini Live (`gemini-3.8-live`) và STT dự phòng |
| `SMARTHOME_SESSION_SECRET` | Khuyên dùng | Khóa bí mật ký phiên đăng nhập cookie/token trên môi trường thật |
| `SMTP_USER`, `GMAIL_APP_PASSWORD` | Tùy chọn | Gửi mã OTP 6 chữ số đăng nhập 2 lớp và khôi phục mật khẩu qua Gmail |
| `SMTP_HOST`, `SMTP_PORT` | Tùy chọn | Máy chủ SMTP gửi thư (mặc định Gmail TLS) |
| `MQTT_BROKER_HOST`, `MQTT_BROKER_PORT` | Tùy chọn | Địa chỉ broker MQTT kết nối ESP8266 (mặc định cổng `1883`) |
| `SMARTHOME_HARDWARE_API_KEY` | Tùy chọn | Khóa xác thực header `X-Hardware-Key` cho endpoint phần cứng ESP8266 |
| `SMARTHOME_DATA_DIR`, `SMARTHOME_SQLITE_PATH` | Tùy chọn | Chỉ định thư mục dữ liệu / đường dẫn tệp SQLite (rất hữu ích khi chạy cổng test `8097` cô lập) |
| `SMARTHOME_BOARD_HEARTBEAT_TIMEOUT_SEC` | Tùy chọn | Ngưỡng thời gian (giây) coi mạch ESP8266 là mất kết nối (mặc định `30`) |
| `VOICE_AUTH_OWNER_EMAIL` | Tùy chọn | Email tài khoản Chủ nhà Cấp 1 mặc định |

---

## 2. Khởi Động Máy Chủ Cục Bộ & Truy Cập Mạng

### 2.1. Chạy máy chủ Production cổng `8088`
- **Chỉ trên máy cục bộ (`localhost`):**
  ```powershell
  python -X utf8 -m uvicorn backend.server:app --host 127.0.0.1 --port 8088
  ```
- **Cho phép mạch ESP8266 và điện thoại trong cùng mạng LAN kết nối trực tiếp:**
  ```powershell
  python -X utf8 -m uvicorn backend.server:app --host 0.0.0.0 --port 8088
  ```
- **Kiểm tra sức khỏe sau khi khởi động:**
  - `GET http://127.0.0.1:8088/api/health` $\rightarrow$ HTTP `200`
  - `GET http://127.0.0.1:8088/api/version` $\rightarrow$ trả về JSON `version: "3.8.0"`, `single_voice: "Aoede"`

### 2.2. Chạy bằng Docker Compose (Tùy chọn)
```powershell
docker compose up --build -d
docker compose logs -f smarthome-voice-ai
```
Container dùng ảnh nền `python:3.11-slim`, tự gắn volume `./backend/data:/app/backend/data` và chạy `HEALTHCHECK` mỗi 30 giây tới `/api/state`.

### 2.3. Công khai HTTPS bằng Tailscale Funnel & Chuyển hướng Vercel
Hệ thống vận hành theo mô hình **Máy chủ tại chỗ (On-Premise Laptop :8088) + Kênh HTTPS công khai miễn phí**:
1. **Tailscale Funnel (`1.104.6`):** Chuyển tiếp HTTPS từ `https://laptop-6i654f8c.tail3020d6.ts.net` về `http://127.0.0.1:8088`:
   ```powershell
   tailscale funnel --bg 8088
   tailscale funnel status
   ```
2. **Vercel Redirect ([`vercel.json`](../../vercel.json)):** Tên miền dễ nhớ `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app` thực hiện chuyển hướng vĩnh viễn (`308`) toàn bộ đường dẫn `/:path*` sang máy chủ Tailscale Funnel để phục vụ đầy đủ WebSocket `/ws`, `SSE` `/api/events` và SQLite cục bộ.
   ```powershell
   vercel --prod
   ```
3. **Xác minh 3 lớp sau triển khai:**
   - Local: `http://127.0.0.1:8088/api/version`
   - Tailscale Funnel: `https://laptop-6i654f8c.tail3020d6.ts.net/api/version`
   - Vercel URL: `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/api/version`

---

## 3. Sao Lưu & Phục Hồi Cơ Sở Dữ Liệu SQLite WAL

Do cơ sở dữ liệu chạy ở chế độ `WAL` (`smarthome.db`, `smarthome.db-wal`, `smarthome.db-shm`), **không nên** chỉ sao chép thô một tệp `.db` khi có giao dịch đang ghi mà hãy dùng API `sqlite3.Connection.backup()` (đảm bảo toàn vẹn giao dịch ngay cả khi server đang chạy):

### Sao lưu an toàn (Online Backup)
```powershell
python -X utf8 -c "import sqlite3, pathlib; src=sqlite3.connect(r'backend/data/smarthome.db'); dst=sqlite3.connect(r'backend/data/smarthome_backup.db'); src.backup(dst); dst.close(); src.close(); print('BACKUP_OK')"
```

### Phục hồi từ bản sao lưu
1. Dừng máy chủ `uvicorn` đang chạy trên cổng `8088`.
2. Đổi tên (lưu dự phòng) bộ tệp hiện tại `smarthome.db`, `smarthome.db-wal`, `smarthome.db-shm`.
3. Chép bản sao lưu sạch về `backend/data/smarthome.db`.
4. Khởi động lại máy chủ và kiểm tra `/api/health` + `/api/version`.

---

## 4. Quy Trình Triển Khai An Toàn Với Khóa `DEPLOY.lock`

Khi hợp nhất nhánh vào `master` và cập nhật máy chủ production, bắt buộc tuân thủ trình tự sau để tránh xung đột giữa các phiên làm việc song song:

1. **Tạo khóa triển khai:** Kiểm tra và tạo tệp `C:\Users\LENOVO\datn-wt\DEPLOY.lock` (nếu khóa đang tồn tại thì chờ tiến trình khác hoàn tất, không ghi đè).
2. **Sao lưu DB Production:** Chạy online backup SQLite tạo tệp có dấu thời gian trước khi cập nhật mã nguồn.
3. **Hợp nhất không ép buộc (Fast-Forward Only):**
   - Chạy `git fetch origin`, đảm bảo nhánh tính năng đã vượt qua `pytest` với `0` lỗi mới.
   - Chuyển sang `master`, chạy `git merge --ff-only <branch>` và `git push origin master` (tuyệt đối không `--force`).
4. **Cập nhật thư mục Production:** Chạy `git pull --ff-only` trên checkout production.
5. **Khởi động lại có điều kiện:**
   - Nếu có thay đổi mã `backend/` hoặc `web/`: khởi động lại tiến trình ẩn cổng `8088` và cập nhật Vercel nếu thay đổi `vercel.json`/`web/public/`.
   - Nếu chỉ cập nhật tài liệu (`docs/`, `README.md`) hoặc biên dịch `app/` (APK): không cần restart cổng `8088`, vẫn gọi kiểm tra `/api/version` và `/api/health`.
6. **Gỡ khóa:** Xóa `C:\Users\LENOVO\datn-wt\DEPLOY.lock` ngay sau khi xác minh xanh.

---

## 5. Quy Trình Kiểm Thử Tự Động Toàn Diện

> **Quy tắc cô lập:** Mọi kiểm thử trình duyệt và kiểm thử APK đều chạy trên một bản sao cơ sở dữ liệu tạm và cổng riêng **`8097`**, sử dụng tài khoản kiểm thử tạm thời và xóa sạch sau khi kiểm thử — **không bao giờ chạm DB production cổng `8088`**.

### 5.1. Kiểm thử Backend, Voice & Phần cứng (`pytest`)
Luôn gắn `--timeout` (từ `pytest-timeout 2.4.0`) để tránh treo test:

```powershell
# Kiểm thử nhanh nhóm hợp đồng phần cứng PCB-Direct, Servo & In 3D
python -m pytest -q --timeout=120 \
  tests/test_hw_contract_6devices_20261120.py \
  tests/test_pcbdirect_agyhw12.py \
  tests/test_servodoor_agyhw13.py \
  tests/test_lessplastic_agyhw14.py

# Kiểm thử đầy đủ toàn bộ bộ test (chỉ định thư mục tạm ngoài repo)
python -m pytest -q --timeout=180 --basetemp="C:\Temp\pytest_sh"
```

### 5.2. Kiểm thử Giao diện Web Headless (`Playwright 1.63.0`)
- Chạy Chromium ở chế độ ẩn (`headless=True`), tối đa 2 trình duyệt đồng thời, giữ RAM hệ thống dưới `85%`.
- Kiểm tra đủ 2 kích thước màn hình (`1366×768` desktop và `412×915` mobile cảm ứng), 2 chế độ Sáng/Tối trên các tuyến `/`, `/automation`, `/auth`, `/logs`, `/wokwi`, `/app`.
- Tiêu chí đạt: `0` lỗi console, `0` lỗi HTTP `>= 400`, `0` tràn ngang, 100% nhãn tiếng Việt.

### 5.3. Biên dịch & Kiểm thử Ứng dụng Android APK (`lightbuild` + `adb`)
```powershell
# 1. Biên dịch APK từ thư mục app/
Set-Location app
lightbuild --plain build app

# 2. Kiểm tra thiết bị Android (yêu cầu Android 8.0+ / minSdk 26) hoặc Emulator headless API 34
& "C:\Users\LENOVO\AppData\Local\Android\Sdk\platform-tools\adb.exe" devices -l

# 3. Chuyển tiếp cổng test 8097 từ máy chủ cục bộ vào điện thoại/emulator
& "C:\Users\LENOVO\AppData\Local\Android\Sdk\platform-tools\adb.exe" reverse tcp:8097 tcp:8097

# 4. Cài đặt APK và theo dõi logcat đảm bảo 0 crash / 0 ANR
& "C:\Users\LENOVO\AppData\Local\Android\Sdk\platform-tools\adb.exe" install -r <duong_dan_apk>
```

> **Lưu ý về tệp APK:** Tệp `.apk` biên dịch ra **không commit lên Git** mà được lưu trữ/bàn giao ngoài kho mã nguồn (ví dụ thư mục bàn giao đồ án), giữ cho kho Git luôn gọn nhẹ.

---

## 6. Tài Liệu Liên Quan

- [Hướng dẫn nạp firmware USB & cài đặt Wi-Fi runtime (`CAI_DAT_WIFI_VA_NAP_USB.md`)](CAI_DAT_WIFI_VA_NAP_USB.md)
- [Kiến trúc hệ thống chi tiết (`KIEN_TRUC_HE_THONG.md`)](../kien_truc/KIEN_TRUC_HE_THONG.md)
- [Công nghệ & phiên bản phần mềm (`CONG_NGHE_VA_PHIEN_BAN.md`)](../kien_truc/CONG_NGHE_VA_PHIEN_BAN.md)
- [Hướng dẫn sử dụng cuối (`USER_GUIDE.md`)](../../USER_GUIDE.md)
