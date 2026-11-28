# Công Nghệ, Phần Mềm & Phiên Bản Sử Dụng (`CONG_NGHE_VA_PHIEN_BAN.md`)

Tài liệu này tổng hợp đầy đủ mọi ngôn ngữ lập trình, framework, thư viện, công cụ biên dịch, thiết kế cơ khí/PCB/3D, kiểm thử và triển khai đang được sử dụng thực tế trong dự án **Smart Home Voice AI** (API `v3.8.0`, bản phát hành `v1.0` / `agyclean15`). Toàn bộ số hiệu phiên bản dưới đây được đo trực tiếp từ máy chủ phát triển LENOVO và các tệp cấu hình nguồn (`requirements.txt`, `firmware/esp8266_smarthome/platformio.ini`, `app/project.lightbuild.yaml`, `app/app/lightbuild.yaml`, `app/app-core/lightbuild.yaml`, `web/vendor/three.min.js`).

---

## 1. Môi Trường Nền & Công Cụ Cốt Lõi

| Thành phần | Phiên bản thực đo / cấu hình | Nguồn xác minh | Vai trò trong dự án |
| :--- | :--- | :--- | :--- |
| **Python** | **`3.14.7`** *(Anaconda 64-bit; hỗ trợ tối thiểu `3.11+`, Docker dùng `python:3.11-slim`)* | `python --version`, [`Dockerfile`](../../Dockerfile) | Chạy máy chủ Backend FastAPI, bộ máy tự động hóa, kiểm thử `pytest`, kịch bản sinh phần cứng/báo cáo |
| **SQLite 3** | **`3.53.2`** *(chế độ `WAL`, `foreign_keys = ON`)* | `sqlite3.sqlite_version` | Cơ sở dữ liệu quan hệ 3NF lưu phiên, tài khoản, thiết bị, 2 bể tự động hóa và nhật ký |
| **Node.js** | **`v26.7.0`** | `node --version` | Hỗ trợ công cụ Vercel CLI và tiện ích web |
| **Git** | **`2.50.0.windows.1`** | `git --version` | Quản lý mã nguồn, worktree, phân nhánh và lịch sử phát hành |

---

## 2. Backend, AI Giọng Nói & Thời Gian Thực (`backend/`)

### 2.1. Thư viện Python (`requirements.txt` & môi trường thực chạy)

| Thư viện | Phiên bản thực cài | Ràng buộc `requirements.txt` | Vai trò kỹ thuật |
| :--- | :---: | :---: | :--- |
| **`fastapi`** | **`0.141.1`** | `>=0.115.0` | Framework API bất đồng bộ (REST, SSE, WebSocket, phục vụ trang tĩnh) |
| **`uvicorn`** | **`0.53.0`** | `>=0.32.0` | Máy chủ ASGI chạy ứng dụng cổng `8088` (production) và `8097` (test) |
| **`starlette`** | **`1.6.0`** | phụ thuộc `fastapi` | Lõi routing, middleware bảo mật, SSE/WebSocket |
| **`pydantic`** | **`2.13.4`** | phụ thuộc `fastapi` | Xác thực schema dữ liệu vào/ra API |
| **`aiosqlite`** | **`0.22.1`** | cài sẵn môi trường | Giao tiếp SQLite bất đồng bộ hỗ trợ `WAL` |
| **`paho-mqtt`** | **`2.2.0`** | cài sẵn môi trường | Cầu nối MQTT Pub/Sub hai chiều tới vi điều khiển ESP8266 |
| **`google-genai`** | **`2.33.0`** | `>=2.3.0` | SDK kết nối Gemini Live API thời gian thực và STT dự phòng |
| **`websockets`** | **`15.0.1`** | `>=13.0` | Luồng WebSocket âm thanh hai chiều `/ws` (PCM 16kHz vào / 24kHz ra) |
| **`httpx`** | **`0.28.1`** | `>=0.27.0` | HTTP client bất đồng bộ cho proxy, kiểm tra sức khỏe và đồng bộ cloud |
| **`python-dotenv`** | **`1.2.2`** | `>=1.0.0` | Nạp biến môi trường cục bộ từ tệp `.env` (không commit Git) |
| **`numpy`** | **`2.5.3`** | `>=1.26.0` | Xử lý mảng tín hiệu âm thanh PCM, VAD và trích xuất đặc trưng DSP |
| **`onnxruntime`** | **`1.30.0`** | `>=1.19.0` | Chạy suy luận mô hình ONNX cục bộ (khử nhiễu/trích xuất đặc trưng giọng) |
| **`qrcode`** | **`8.2`** | `>=7.4.2` | Sinh mã QR mời Khách/Thành viên dùng một lần (SVG/PNG) |
| **`scipy`** | **`1.18.1`** | cài sẵn môi trường | Xử lý tín hiệu số âm thanh (lọc, tái lấy mẫu) |
| **`soundfile`** | **`0.14.0`** | cài sẵn môi trường | Đọc/ghi mẫu âm thanh `.wav` cho kiểm thử giọng nói |
| **`Pillow`** | **`12.3.0`** | cài sẵn môi trường | Xử lý ảnh sơ đồ và ảnh minh họa |

### 2.2. Mô hình AI Giọng Nói Tiếng Việt

| Thành phần AI | Mã mô hình / Giọng đọc | Nguồn cấu hình | Vai trò |
| :--- | :--- | :--- | :--- |
| **Gemini Live thời gian thực** | **`gemini-3.8-live`** | [`backend/live/gemini_bridge.py`](../../backend/live/gemini_bridge.py) | Hiểu khẩu lệnh tiếng Việt tự nhiên, gọi Function Tools và phản hồi tức thì |
| **Giọng đọc tiếng Việt duy nhất** | **`Aoede`** *(24 kHz Mono 16-bit PCM)* | `backend/server.py`, `backend/live/tts_rejection_vi.py` | Phát âm thanh phản hồi tiếng Việt đồng nhất trên Web & Android (có bộ đệm SQLite `aoede_audio_cache`) |
| **STT dự phòng trên cloud** | **`gemini-3.1-flash-lite`** *(chuỗi dự phòng)* | [`backend/voice/gemini_stt.py`](../../backend/voice/gemini_stt.py) | Chuyển giọng nói tiếng Việt sang văn bản khi không dùng luồng Live trực tiếp |

---

## 3. Giao Diện Web & Bản Sao Số 3D (`web/`)

| Công nghệ / Thư viện | Phiên bản | Vị trí trong repo | Vai trò |
| :--- | :---: | :--- | :--- |
| **HTML5 / CSS3 / Vanilla JS (ES6+)** | Chuẩn trình duyệt hiện đại | [`web/`](../../web/) | Giao diện không cần bước bundler nặng, hỗ trợ chế độ Sáng/Tối, responsive desktop + mobile |
| **Three.js** | **`r128`** | [`web/vendor/three.min.js`](../../web/vendor/three.min.js) | Kết xuất mô hình biệt thự 3D Digital Twin (`web/models/smarthome_villa.glb`), 14 module và 40 tuyến dây 3D |
| **Three.js GLTFLoader** | **`r128`** | [`web/vendor/GLTFLoader.js`](../../web/vendor/GLTFLoader.js) | Nạp mô hình `.glb` xuất từ Blender lên trình duyệt |
| **Wokwi Elements** | Đóng gói cục bộ | [`web/wokwi-elements.bundle.js`](../../web/wokwi-elements.bundle.js) | Hiển thị linh kiện tương tác trên trang hướng dẫn đấu nối `/wokwi` |
| **Service Worker PWA** | Chuẩn Web API | [`web/sw.js`](../../web/sw.js), [`web/mobile/index.html`](../../web/mobile/index.html) | Giao diện di động `/app` và trang ngoại tuyến `/offline` |

---

## 4. Ứng Dụng Android Gốc (`app/`)

Cấu hình chuẩn đọc từ [`app/project.lightbuild.yaml`](../../app/project.lightbuild.yaml), [`app/app/lightbuild.yaml`](../../app/app/lightbuild.yaml) và [`app/app-core/lightbuild.yaml`](../../app/app-core/lightbuild.yaml):

| Thành phần Android | Phiên bản | Vai trò |
| :--- | :---: | :--- |
| **Ngôn ngữ Kotlin** | **`2.3.20`** | Toàn bộ mã nguồn ứng dụng (`vn.edu.hust.seee.smarthome`) |
| **Java / JVM Target** | **`JDK 17`** | Mục tiêu biên dịch bytecode JVM |
| **Lightbuild** | **CLI `0.0.1`** / schema **`0.0.30`** | Hệ thống build Android nhẹ (`lightbuild --plain build app`) |
| **Android CLI / SDK** | **CLI `1.1.16919734`**, Build-Tools **`36.0.0`** | Biên dịch và đóng gói APK |
| **Mức API Android** | `compileSdk = 36`, `targetSdk = 34`, `minSdk = 26` *(Android 8.0+)* | Hỗ trợ đầy đủ máy Android 8.0 trở lên, bảo đảm quyền micro/camera hiện đại |
| **ADB (Android Debug Bridge)** | **`1.0.41`** *(Platform-Tools `37.0.1-15733141`)* | Cài đặt APK qua USB, chuyển tiếp cổng `adb reverse` và chụp kiểm thử |
| **`androidx.compose.ui:ui`** (+ tooling) | **`1.10.4`** | Giao diện khai báo Jetpack Compose |
| **`androidx.compose.material3:material3`** | **`1.4.0`** | Hệ thống thiết kế Material 3 (Sáng/Tối) |
| **`androidx.navigation3:navigation3-ui` & `-runtime`** | **`1.0.1`** | Điều hướng giữa cổng đăng nhập, màn hình chính, quét QR và quên mật khẩu |
| **`androidx.lifecycle:lifecycle-*-compose`** | **`2.10.0`** | Quản lý trạng thái ViewModel & vòng đời (`runtime-ktx`, `runtime-compose`, `viewmodel-compose`, `viewmodel-navigation3`) |
| **`androidx.core:core-ktx`** | **`1.18.0`** | Tiện ích chuẩn AndroidX Kotlin |
| **`androidx.activity:activity-compose`** | **`1.13.0`** | Tích hợp Activity với Jetpack Compose |
| **Bộ kiểm thử Android** | `junit:4.13.2`, `kotlinx-coroutines-test:1.10.2`, `androidx.test:core:1.7.0`, `ext:junit:1.3.0`, `runner:1.7.0`, `espresso-core:3.7.0`, `ui-test-junit4:1.10.4` | Kiểm thử đơn vị ViewModel & kiểm thử giao diện Instrumented |

---

## 5. Firmware Vi Điều Khiển ESP8266 (`firmware/esp8266_smarthome/`)

Cấu hình chuẩn đọc từ [`firmware/esp8266_smarthome/platformio.ini`](../../firmware/esp8266_smarthome/platformio.ini):

| Thành phần Firmware | Phiên bản | Vai trò |
| :--- | :---: | :--- |
| **PlatformIO Core (`pio`)** | **`6.2.0`** | Biên dịch, quản lý thư viện và nạp firmware qua USB |
| **Nền tảng & Bo mạch** | `platform = espressif8266`, `board = nodemcuv2`, `framework = arduino` | Nhắm đúng bo mạch **NodeMCU ESP8266 v2 Amica** (`ESP-12E/F`, chip USB `CP2102`) |
| **Công cụ nạp `tool-esptoolpy`** | **`2.40900.250804`** | Nạp nhị phân qua cổng Serial USB |
| **`knolleary/PubSubClient`** | **`^2.8`** | Giao thức MQTT hai chiều (kèm LWT phát hiện mất kết nối) |
| **`bblanchon/ArduinoJson`** | **`^6.21.5`** | Phân tích JSON cấu hình `/wifi_config.json` (LittleFS), lệnh `WIFI_CONFIG` và gói tin telemetry |
| **`adafruit/DHT sensor library`** | **`^1.4.6`** | Đọc nhiệt độ & độ ẩm từ cảm biến `DHT11` (`D2 / GPIO4`) |
| **`adafruit/Adafruit Unified Sensor`** | **`^1.1.14`** | Thư viện nền bắt buộc của `DHT sensor library` |
| **LittleFS + `ESP8266WebServer` + `Servo`** | Tích hợp trong Arduino Core ESP8266 | Lưu cấu hình Wi-Fi runtime `/wifi_config.json`, phục vụ API ngoại tuyến cổng `80`, điều khiển Servo SG90 |

---

## 6. Thiết Kế Mạch PCB, Cơ Khí 3D & In 3D (`hardware/`)

| Phần mềm CAD / CAM / 3D | Phiên bản thực đo | Vai trò trong dự án |
| :--- | :---: | :--- |
| **KiCad CLI** | **`10.0.6`** | Thiết kế sơ đồ nguyên lý & mạch in 1 lớp **PCB Hub DIY v3** (`100 × 80 × 1.6 mm`, `51 footprints`), xuất Gerber/PDF 1:1 Toner Transfer và kiểm tra `0 ERC / 0 DRC` |
| **FreeCAD** | **`1.1.4`** *(Revision `20260928`)* | Mô hình hóa tham số vỏ nhà Mica 3 mm cắt laser và bộ vỏ in 3D v2 lắp mộng `51` chi tiết / `83` bản thể (`0` va chạm BRep) |
| **Blender** | **`5.2.2 LTS`** *(build `2026-09-15`)* | Dựng mô hình biệt thự 3D Digital Twin (`web/models/smarthome_villa.glb`) và cảnh lắp ghép 40 dây 3D (`hardware/blender/system_wired_assembly.glb`) |
| **PrusaSlicer** | **`2.9.7`** | Đóng gói 16 bàn in `.3mf` nhúng sẵn thông số (`9% Gyroid`, `2/3` thành, `0% support`), đo chính xác `660.64 g` PLA và thời gian in `73g 23p 49s` |

---

## 7. Kiểm Thử Tự Động, Triển Khai & Xuất Báo Cáo

| Công cụ / Dịch vụ | Phiên bản thực đo | Vai trò |
| :--- | :---: | :--- |
| **`pytest` & `pytest-timeout`** | **`9.1.1`** / **`2.4.0`** | Chạy bộ kiểm thử hồi quy Backend, RBAC, Voice NLU, phần cứng PCB-Direct và in 3D có chống treo từng test |
| **Playwright** | **`1.63.0`** | Kiểm thử trình duyệt Chromium headless trên desktop (`1366×768`) và di động (`412×915`), Sáng/Tối |
| **Tailscale (Funnel)** | **`1.104.6`** | Mở kênh HTTPS công khai an toàn từ máy chủ nội bộ cổng `8088` ra Internet (`laptop-6i654f8c.tail3020d6.ts.net`) không cần mở port router |
| **Vercel CLI** | **`59.16.0`** | Triển khai tên miền HTTPS ngắn gọn (`do-an-tot-nghiep-smart-home-voice-a.vercel.app`) chuyển hướng 308 tới Tailscale Funnel |
| **Docker** | **`28.1.1`** *(build `4eba377`)* | Đóng gói container tái lập (`Dockerfile`, `docker-compose.yml`) |
| **`python-docx` / `PyMuPDF` / `pywin32` / `pandoc`** | **`1.2.0`** / **`1.28.2`** / **`312`** / **`3.12`** | Sinh Báo cáo Đồ án Tốt nghiệp `.docx` tự động, cập nhật trường mục lục Word COM ẩn, xuất `.pdf` và kiểm định trang bằng hình ảnh |

---

## 8. Tài Liệu Liên Quan

- [Kiến trúc hệ thống chi tiết (`KIEN_TRUC_HE_THONG.md`)](KIEN_TRUC_HE_THONG.md)
- [Hướng dẫn nạp firmware USB & cài Wi-Fi runtime (`CAI_DAT_WIFI_VA_NAP_USB.md`)](../huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md)
- [Hướng dẫn vận hành & triển khai (`VAN_HANH_VA_TRIEN_KHAI.md`)](../huong_dan/VAN_HANH_VA_TRIEN_KHAI.md)
- [Tổng quan phần cứng & in 3D (`TONG_QUAN_PHAN_CUNG_VA_IN_3D.md`)](../phan_cung/TONG_QUAN_PHAN_CUNG_VA_IN_3D.md)
