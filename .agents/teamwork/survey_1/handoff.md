# Báo Cáo Khảo Sát Kỹ Thuật (Phase 0 - Mảng 1)
## Deploy Vercel, HTTPS Tunnel & QR Guest Handshake

**Người thực hiện:** `survey_1` (Teamwork Explorer)  
**Ngày thực hiện:** 2026-11-04  
**Dự án:** Hệ thống Nhà Thông Minh Điều Khiển Bằng Giọng Nói AI (Đồ Án Tốt Nghiệp)  
**Tài liệu tham chiếu:** `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md`

---

## 1. Observation (Dữ Liệu & Thực Nghiệm Khảo Sát Trực Tiếp)

### 1.1. Khảo sát Cấu hình Git & Deploy Vercel
- **Remote Git & Branch:**
  - Lệnh kiểm tra: `git status`, `git remote -v`
  - Kết quả: Branch hiện tại là `master`, upstream là `origin/master`.
  - Remote URL: `https://github.com/nep94121-lab/do-an-tot-nghiep-smart-home-voice-ai.git`.
  - GitHub CLI (`gh`): Đã đăng nhập tài khoản `nep94121-lab` (Keyring HTTPS), đầy đủ scopes: `'gist', 'read:org', 'repo'`.
- **Vercel CLI & Trạng thái Tài khoản:**
  - Phiên bản Vercel CLI: `59.16.0` (chạy trên Node.js `26.7.0`).
  - Tài khoản Vercel: Đã đăng nhập với tài khoản `nep94121-8303` (Scope: `tuananhs-projects-8aea56ce`).
  - File cấu hình `vercel.json`: **Chưa tồn tại** trong thư mục gốc dự án.
  - Trạng thái liên kết dự án: Dự án chưa được link vào Vercel (`Error: Project is not linked. Run 'vercel link' first`).
  - Danh sách projects hiện có trên scope: `web-ca-nhan-nguyen-tuan-anh`, `vinh-cat-web`, `serein-deploy`, `smart-stadium-trong-dong-3d`, `bang-ky-ten`, `ai-rule-eval-dashboard`, `football-betting-sandbox`, `on-tap-ai-ml`, v.v. (Chưa có project cho Đồ án Voice AI).
- **Cấu trúc Tệp Tĩnh (Frontend) & Định tuyến Backend:**
  - Thư mục `simulator/static/`: Chứa các trang giao diện Web gồm `index.html` (Bảng điều khiển 3D Ngôi nhà), `auth.html` (Quản trị Xác thực 3 Lớp), `guest_enroll.html` (Đăng ký khách qua QR), `logs.html` (Truy vấn Nhật ký & Tri thức RAG), `wokwi.html` (Mô phỏng Mạch ESP8266 Wokwi), kèm các thư mục tài nguyên `css/`, `js/`, `models/`, `vendor/`.
  - Thư mục `mobile_app/`: Chứa `index.html` (Giao diện PWA chuyên biệt dành cho Điện thoại, được FastAPI phục vụ tại endpoint `/app`).
  - Backend FastAPI (`simulator/server.py`): Đang chạy trên cổng `8088` (`0.0.0.0:8088`), phục vụ WebSocket `/ws`, cơ sở dữ liệu SQLite cục bộ `simulator/data/smarthome.db`, mô đun xử lý âm học và nhận dạng giọng nói `simulator/voice_auth.py`, cùng các API điều khiển thiết bị IoT.

### 1.2. Khảo sát HTTPS Tunnel, LAN IP & ADB Reverse
- **FastAPI Server (Cổng 8088):**
  - Trạng thái kiểm tra bằng `Get-NetTCPConnection -LocalPort 8088`: Đang lắng nghe ở `0.0.0.0:8088` (State: `Listen`).
  - Gọi thực nghiệm: `curl.exe -s http://127.0.0.1:8088/api/state` -> Trả về mã HTTP `200 OK`, JSON trạng thái đầy đủ 7 thiết bị và telemetry cảm biến DHT11/Độ ẩm đất.
- **HTTPS Tunnel (OpenSSH `localhost.run`):**
  - Công cụ OpenSSH: `OpenSSH_for_Windows_9.5p2, LibreSSL 3.8.2`.
  - Khởi tạo tunnel: `ssh -o StrictHostKeyChecking=no -R 80:127.0.0.1:8088 nokey@localhost.run`.
  - Tên miền công cộng được cấp phát thực tế: `https://04f0beba8cdda9.lhr.life`.
  - Kiểm tra gọi qua HTTPS Tunnel:
    - `curl.exe -s https://04f0beba8cdda9.lhr.life/api/state` -> Trả về HTTP `200 OK` kèm toàn bộ dữ liệu trạng thái.
    - `curl.exe -s -o NUL -w "%{http_code}" https://04f0beba8cdda9.lhr.life/app` -> Trả về HTTP `200`.
  - Hỗ trợ giao thức: localhost.run kết thúc TLS tại cổng 443 và hỗ trợ chuyển mạch HTTP/1.1 WebSocket Upgrades, đảm bảo trình duyệt di động cấp quyền truy cập Microphone/AudioContext do đạt chuẩn HTTPS.
- **Địa chỉ LAN IP:**
  - Card mạng Wi-Fi của máy chủ có địa chỉ IPv4: `192.168.2.39`.
  - Gọi thực nghiệm: `curl.exe -s -o NUL -w "%{http_code}" http://192.168.2.39:8088/api/state` -> Trả về HTTP `200`.
  - Cho phép mọi thiết bị (laptop, tablet, điện thoại) trong mạng Wi-Fi nội bộ truy cập trực tiếp không qua internet.
- **Kết nối ADB Reverse qua USB:**
  - Kiểm tra thiết bị: `adb devices -l` phát hiện điện thoại vật lý Samsung Galaxy S9:
    `2223e8784b0c7ece device usb:1-2 product:starltexx model:SM_G960F device:starlte`.
  - Thiết lập đảo cổng: `adb reverse tcp:8088 tcp:8088`.
  - Kiểm tra danh sách: `adb reverse --list` trả về `UsbFfs tcp:8088 tcp:8088`.
  - Cho phép điện thoại cắm USB mở trực tiếp `http://localhost:8088/app` với độ trễ 0ms, không phụ thuộc vào internet hay mạng Wi-Fi.
- **Endpoint sinh mã QR (`simulator/api/routes_qr.py`):**
  - Endpoints: `GET /api/auth3/guest_qr_current` và alias `/api/auth3/qr/generate`.
  - Nhận tham số: `host` hoặc `host_url` (mặc định là `localhost:8088`).
  - Thử nghiệm gọi: `curl.exe -s "http://127.0.0.1:8088/api/auth3/guest_qr_current?host=https://04f0beba8cdda9.lhr.life"`:
    - Trả về: `"full_url": "https://04f0beba8cdda9.lhr.life/guest_enroll?token=...&window=...&dur=1d"`.
    - Trả về chuỗi SVG chuẩn: `"qr_svg": "<svg..."`.
  - Điểm phát hiện: Dòng 109-112 trong `simulator/api/routes_qr.py`: Nếu tham số `chosen_host` không có tiền tố `http://` hoặc `https://`, code tự động gán `http://{chosen_host}`. Do đó, nếu truyền domain tunnel như `04f0beba8cdda9.lhr.life` mà thiếu scheme, link sẽ bị gắn `http://` thay vì `https://`.

### 1.3. Khảo sát TOTP Guest Handshake (`simulator/auth/qr_totp_mixin.py`)
- **Vị trí Hàm:** `consume_guest_handshake` tại dòng 89-198 của `simulator/auth/qr_totp_mixin.py`.
- **Cơ chế xác thực thời gian hiện tại:**
  - Dòng 116: `cur_window = int(time.time() // 10)`. Mỗi chu kỳ window là đúng 10 giây.
  - Dòng 131: Khi tìm trong fallback HMAC, vòng lặp chỉ kiểm tra: `for w_chk in (cur_window, cur_window - 1):` (tối đa lùi 1 chu kỳ = 10s).
  - Dòng 162-167:
    ```python
    if abs(cur_window - token_win) > 1:
        return {
            "ok": False,
            "error": "Mã QR đã hết hạn 10 giây, vui lòng quét lại mã mới trên màn hình!",
            "status_code": 401,
        }
    ```
- **Lỗi thao tác trên điện thoại:**
  - Thao tác thực tế của người dùng: Giơ điện thoại lên, bật ứng dụng Camera, căn chỉnh mã QR, bấm thông báo mở trình duyệt, tải trang web qua mạng di động/Wi-Fi và gửi POST handshake mất từ **15 đến 45 giây**.
  - Với điều kiện `abs(cur_window - token_win) > 1`, chỉ cần quá 15-20 giây là `cur_window - token_win >= 2`, máy chủ lập tức từ chối và báo lỗi: `"Mã QR đã hết hạn 10 giây, vui lòng quét lại mã mới trên màn hình!"` (HTTP 401).
- **Vấn đề đồng bộ tại Frontend `guest_enroll.js`:**
  - Trong `simulator/static/js/guest_enroll.js` (dòng 128-143): Hàm `initQrHandshake` đọc query param `dur` và `tier`, nhưng **hoàn toàn không đọc** `params.get('token')` từ URL do mã QR truyền vào!
  - Thay vào đó, nó lại gọi `refreshGuestQrNow()` (dòng 141) để fetch một token mới khác từ server rồi handshake token mới đó, dẫn đến hiện tượng lệch pha nếu mạng chậm hoặc token trên điện thoại khác token trên màn hình.

### 1.4. Trạng thái Kiểm thử Hiện tại
- Chạy `python -m pytest tests/test_challenger_m4_dom.py --basetemp=...`: Đạt **36/36 passed** (100% PASS trong 3.03s).
- Chạy `python -m pytest tests/test_milestone_m2_qr_guest.py --basetemp=...`: Đạt **17/17 passed** (100% PASS trong 8.30s).

---

## 2. Logic Chain (Chuỗi Lập Luận Từ Dữ Liệu Đến Kết Luận)

1. **Từ việc Vercel CLI đã đăng nhập (`nep94121-8303`) nhưng chưa có `vercel.json` và chưa link project:**
   - Dự án hoàn toàn có khả năng deploy lên Vercel thông qua lệnh `vercel --prod --yes` theo quy trình chuẩn của skill `deploy-github-vercel`.
   - Vì cấu trúc frontend gồm các trang nằm trong `simulator/static/` và `mobile_app/`, nếu không có file `vercel.json` định nghĩa các `rewrites` / `routes`, Vercel sẽ không biết phục vụ trang nào tại `/`, `/app`, `/auth`, `/guest_enroll`, `/logs`, `/wokwi`.
   - Do đó, giải pháp bắt buộc là khởi tạo file `vercel.json` chứa bản đồ định tuyến chính xác cho 6 trang HTML và các thư mục tĩnh (`/static/`, `/test_audio/`).

2. **Từ đặc thù kiến trúc hệ thống (FastAPI WebSocket + SQLite + AI Audio Model) kết hợp yêu cầu của Sếp:**
   - Backend FastAPI không thể chạy serverless hoàn toàn trên Vercel do yêu cầu kết nối WebSocket hai chiều liên tục với ESP8266/Web và quản lý file SQLite cục bộ.
   - Sếp đã định hướng mô hình kết hợp cực kỳ chuẩn xác: Vercel đóng vai trò Cloud Frontend / Web Showcase, trong khi FastAPI Server chạy tại máy trạm và được kết nối ra bên ngoài qua 3 kênh:
     - Kênh 1: **ADB Reverse (`localhost:8088`)** — Dành cho điện thoại cắm cáp USB trực tiếp, siêu tốc độ, ổn định tuyệt đối khi test thực địa.
     - Kênh 2: **LAN IP (`192.168.2.39:8088`)** — Dành cho các thiết bị cùng mạng Wi-Fi gia đình.
     - Kênh 3: **HTTPS Tunnel (`localhost.run`)** — Cấp domain HTTPS có SSL hợp lệ (`https://*.lhr.life`), hỗ trợ WebSocket và cho phép trình duyệt di động truy cập Microphone để ra lệnh giọng nói và thu âm khách Cấp 3.

3. **Từ việc phân tích hàm `consume_guest_handshake` trong `qr_totp_mixin.py`:**
   - Việc mã QR xoay vòng mỗi 10 giây trên màn hình (để hiển thị đếm lùi trực quan và chống chụp lén) là tính năng UI tốt.
   - Tuy nhiên, việc áp dụng dung sai kiểm tra `abs(cur_window - token_win) <= 1` (chỉ cho phép trễ tối đa 10~20s) tại backend là nguyên nhân trực tiếp khiến người dùng quét mã trên điện thoại luôn bị timeout giữa chừng.
   - Giải pháp là nới rộng thời gian chấp nhận token (Handshake Acceptance Window) lên **180 giây (3 phút = 18 windows)**.
   - Tính an toàn của hệ thống vẫn được bảo toàn 100% nhờ cơ chế **Single-Use Token** (`store.add(clean_tok)`): Mỗi token chỉ được sử dụng đúng 1 lần duy nhất, nếu kẻ gian quét lại hoặc replay request sẽ lập tức bị chặn với lỗi `Single-Use Token` (HTTP 400).
   - Đồng thời, cập nhật `guest_enroll.js` để đọc trực tiếp `token` từ URL query params khi mở qua mã QR, đảm bảo trải nghiệm tức thì.

---

## 3. Caveats (Giới Hạn Khảo Sát & Giả Định)

1. **Tính biến động của subdomain OpenSSH `localhost.run`:**
   - Miền công cộng miễn phí do `localhost.run` cấp (`*.lhr.life`) sẽ thay đổi mỗi khi ngắt và mở lại phiên SSH.
   - Để không phải sửa code thủ công mỗi lần chạy lại tunnel, cần lưu trữ URL tunnel hiện tại vào bộ nhớ hoặc file cấu hình tạm `simulator/data/tunnel_info.json` để API `routes_qr.py` tự động đọc.
2. **Quyền Microphone trên trình duyệt di động (WebRTC / AudioContext):**
   - Trình duyệt Chrome / Samsung Internet trên Android bắt buộc trang web phải chạy qua `https://` hoặc `http://localhost` (Secure Context) mới cho phép mở Microphone.
   - Do đó, nếu truy cập qua mạng LAN (`http://192.168.2.39:8088`), một số trình duyệt có thể cảnh báo Secure Context trừ khi người dùng bật cờ `unsafely-treat-insecure-origin-as-secure` trong `chrome://flags`. Truy cập qua HTTPS Tunnel (`https://*.lhr.life`) hoặc ADB Reverse (`http://localhost:8088`) hoàn toàn không bị hạn chế này.

---

## 4. Conclusion & Proposed Architecture (Kết Luận & Đề Xuất Giải Pháp)

### 4.1. Ma trận Giải Pháp Kỹ Thuật (Feature Matrix)

| Thành Phần | Giải Pháp Đề Xuất | File Mã Nguồn Tác Động |
|---|---|---|
| **1. Cấu hình Vercel Deploy** | Tạo `vercel.json` định tuyến 6 trang static, static assets và archify docs. Đẩy code lên GitHub `nep94121-lab` và chạy `vercel --prod --yes`. | `vercel.json`, `PROJECT.md` |
| **2. Tích hợp Đa Kênh Kết Nối** | Hỗ trợ 3 chế độ: ADB Reverse (`localhost:8088`), LAN IP (`192.168.2.39:8088`), và HTTPS Tunnel (`https://*.lhr.life`). | `simulator/server.py`, `simulator/api/routes_qr.py` |
| **3. Cải tiến API Sinh Mã QR** | Nhận diện giao thức HTTPS thông minh, tự động gắn link chuẩn theo kênh host được chọn. Thêm bộ chọn kênh kết nối trên UI. | `simulator/api/routes_qr.py`, `simulator/static/js/auth.js` |
| **4. Nới Rộng Handshake TOTP** | Nới rộng dung sai cửa sổ thời gian trong `consume_guest_handshake` lên 180s (18 windows), duy trì nghiêm ngặt Single-Use Token. | `simulator/auth/qr_totp_mixin.py` |
| **5. Khớp Token Trang Thu Âm Khách** | Cập nhật `guest_enroll.js` đọc `token` từ URL query params khi quét mã QR để handshake tức thì không bị lệch pha. | `simulator/static/js/guest_enroll.js` |

### 4.2. Cấu trúc Đề xuất cho `vercel.json`
```json
{
  "version": 2,
  "cleanUrls": true,
  "routes": [
    { "src": "/static/(.*)", "dest": "/simulator/static/$1" },
    { "src": "/test_audio/(.*)", "dest": "/test_audio/$1" },
    { "src": "/app", "dest": "/mobile_app/index.html" },
    { "src": "/auth", "dest": "/simulator/static/auth.html" },
    { "src": "/guest_enroll", "dest": "/simulator/static/guest_enroll.html" },
    { "src": "/guest-qr", "dest": "/simulator/static/guest_enroll.html" },
    { "src": "/logs", "dest": "/simulator/static/logs.html" },
    { "src": "/wokwi", "dest": "/simulator/static/wokwi.html" },
    { "src": "/archify", "dest": "/docs/kien_truc/smart-home-voice-ai.architecture.html" },
    { "src": "/archify/devops", "dest": "/docs/kien_truc/devops-cicd-pipeline.workflow.html" },
    { "src": "/", "dest": "/simulator/static/index.html" }
  ]
}
```

### 4.3. Đề xuất Sửa Đổi Cụ Thể cho `consume_guest_handshake` (`qr_totp_mixin.py`)
- Thay đổi dòng 131:
  ```python
  # Trước:
  for w_chk in (cur_window, cur_window - 1):
  # Đề xuất: Cho phép kiểm tra lùi tối đa 18 chu kỳ (180 giây)
  for w_chk in range(cur_window, cur_window - 19, -1):
  ```
- Thay đổi dòng 162:
  ```python
  # Trước:
  if abs(cur_window - token_win) > 1:
  # Đề xuất: Dung sai 18 chu kỳ (180s) cho phép thao tác trên điện thoại thoải mái
  if (cur_window - token_win) > 18 or (token_win - cur_window) > 2:
  ```

---

## 5. Verification Method (Phương Pháp Kiểm Chứng Độc Lập)

1. **Kiểm chứng Vercel & Static Routes:**
   - Tạo file `vercel.json` và chạy thử nghiệm cấu trúc file bằng `node -e "JSON.parse(fs.readFileSync('vercel.json'))"`.
   - Kiểm tra `vercel link --yes` và `vercel deploy --dry`.
2. **Kiểm chứng Kết nối Tunnel & LAN:**
   - Chạy lệnh kiểm tra phản hồi từ HTTPS Tunnel:
     `curl.exe -I https://04f0beba8cdda9.lhr.life/api/state` (Đạt mã `200 OK`).
   - Chạy lệnh kiểm tra phản hồi từ LAN IP:
     `curl.exe -I http://192.168.2.39:8088/api/state` (Đạt mã `200 OK`).
   - Chạy lệnh kiểm tra kết nối qua ADB:
     `$env:ADB_LIBUSB=1; & "C:\Users\LENOVO\AppData\Local\Android\Sdk\platform-tools\adb.exe" shell "curl -s -o /dev/null -w %{http_code} http://localhost:8088/api/state"` (Đạt mã `200`).
3. **Kiểm chứng Handshake TOTP Nới Rộng:**
   - Chạy toàn bộ test suite M2 QR Guest:
     `python -m pytest tests/test_milestone_m2_qr_guest.py --basetemp=C:\Users\LENOVO\AppData\Local\Temp\pytest_qr` (Đạt 100% PASS).
   - Thử nghiệm sinh mã token tại thời điểm $T$, đợi 30 giây (vượt quá 10s cũ), sau đó gửi yêu cầu handshake -> Đạt `200 OK` (thay vì bị 401 như trước).
   - Gửi lại token đã handshake lần 2 -> Đạt `400 Bad Request` (`Single-Use Token`).
4. **Kiểm chứng Toàn Vẹn Giao Diện (DOM Challenger):**
   - Chạy `python -m pytest tests/test_challenger_m4_dom.py --basetemp=C:\Users\LENOVO\AppData\Local\Temp\pytest_dom` (Đạt 36/36 PASS).
