# Bản Đồ Khung Xương Dự Án & Hợp Đồng Liên Tầng (`REPO_MAP.md`)

Tài liệu này cung cấp bản đồ cấu trúc mã nguồn hiện hành (`v3.8.0` / `v1.0`, `agyclean15`) giúp kỹ sư và công cụ phát triển định vị nhanh các mô-đun trọng tâm và các hợp đồng giao tiếp liên tầng mà không cần quét toàn bộ kho mã.

---

## 1. Hợp Đồng Liên Tầng Khóa Cứng (Cross-Layer Contracts)

1. **6 Thiết bị chấp hành + 3 Cảm biến trên 10 chân NodeMCU ESP8266 v2 Amica:**
   - Thiết bị: `main_door` (`D1/GPIO5`), `living_room_light` (`D0/GPIO16`), `bedroom_light` (`D4/GPIO2` Active-LOW), `garden_pump` (`D6/GPIO12`), `alarm_siren` (`D8/GPIO15` qua `Q1 S8050`), `speaker_amp` (`D7/GPIO13` + PWM `D3/GPIO0`).
   - Cảm biến: `dht11` (`D2/GPIO4`), `soil_moisture` (`A0/ADC0`, nguồn `3.3V`), `ky037` (`D5/GPIO14`, nguồn `3.3V`).
   - Nguồn sự thật (SSOT): [`hardware/wiring_contract.py`](../../hardware/wiring_contract.py), [`backend/engine/constants_and_time.py`](../../backend/engine/constants_and_time.py), [`backend/auth/tier_permissions.py`](../../backend/auth/tier_permissions.py), [`firmware/esp8266_smarthome/esp8266_smarthome.ino`](../../firmware/esp8266_smarthome/esp8266_smarthome.ino).
2. **8 Chủ đề MQTT chuẩn (`backend/mqtt_bridge.py` $\leftrightarrow$ `esp8266_smarthome.ino`):**
   - `smarthome/cmd/actuate`, `smarthome/cmd/enroll_blink`, `smarthome/sync/pools`
   - `smarthome/telemetry/dht11`, `smarthome/telemetry/soil_moisture`, `smarthome/telemetry/sound`
   - `smarthome/state/report`, `smarthome/status/esp8266`
3. **Kênh thời gian thực:**
   - `GET /api/events` (Server-Sent Events) & `WebSocket /ws` (Gemini Live `gemini-3.8-live`, giọng `Aoede` 24 kHz PCM).

---

## 2. Bản Đồ Các Phân Hệ Chính

### 2.1. Backend FastAPI & CSDL SQLite WAL (`backend/`)
| Mô-đun / Thư mục | Đường dẫn | Trách nhiệm chính |
| :--- | :--- | :--- |
| Máy chủ chính & định tuyến tĩnh | [`backend/server.py`](../../backend/server.py) | Khởi tạo FastAPI `v3.8.0`, phục vụ trang HTML, `/api/health`, `/api/version`, `/ws` |
| Nhóm Router REST API | `backend/api/routes_auth.py`, `routes_devices.py`, `routes_automation.py`, `routes_guest.py`, `routes_qr.py`, `routes_logs.py` | Tách biệt rõ ràng API xác thực, thiết bị, tự động hóa 2 bể, mã mời QR và nhật ký |
| Lõi điều khiển & 2 Bể tự động | [`backend/rule_engine.py`](../../backend/rule_engine.py), [`backend/automation_engine.py`](../../backend/automation_engine.py), [`backend/compound_nlu.py`](../../backend/compound_nlu.py) | Điều phối `execute_device_action`, đánh giá luật tổ hợp `AND`/`OR`, lịch tuần, hẹn giờ |
| Xác thực 3 tầng & Phiên | [`backend/auth/tier_permissions.py`](../../backend/auth/tier_permissions.py), [`backend/auth/session_store.py`](../../backend/auth/session_store.py), [`backend/auth/guest_invites.py`](../../backend/auth/guest_invites.py), [`backend/auth/owner_pin.py`](../../backend/auth/owner_pin.py) | Kiểm tra quyền Cấp 1/2/3 phía server, cookie `HttpOnly`, PIN PBKDF2-SHA256, mã QR dùng 1 lần |
| Giọng nói AI & Chính sách `agyfix11` | [`backend/live/gemini_bridge.py`](../../backend/live/gemini_bridge.py), [`backend/live/echo_and_speech_guard.py`](../../backend/live/echo_and_speech_guard.py), [`backend/voice/vietnamese_policy.py`](../../backend/voice/vietnamese_policy.py), [`backend/ai_tool_registry.py`](../../backend/ai_tool_registry.py) | Cầu nối Gemini Live `Aoede`, chống vọng tiếng, xác nhận 1 lần lệnh tùy chỉnh & phản hồi ngắn gọn |
| Lưu trữ SQLite WAL & MQTT | [`backend/database_sqlite.py`](../../backend/database_sqlite.py), [`backend/db_migrations.py`](../../backend/db_migrations.py), [`backend/mqtt_bridge.py`](../../backend/mqtt_bridge.py), [`backend/realtime_hub.py`](../../backend/realtime_hub.py) | 25 bảng 3NF WAL, cầu nối MQTT tới ESP8266 và phát sóng `SSE` `< 1s` |

### 2.2. Giao Diện Web 3D Digital Twin & Mobile PWA (`web/`)
- **Trang HTML:** `web/index.html` (`/`), `web/mobile/index.html` (`/app`), `web/automation.html` (`/automation`), `web/auth.html` (`/auth`), `web/logs.html` (`/logs`), `web/wokwi.html` (`/wokwi`), `web/login.html` (`/login`), `web/register.html` (`/register`), `web/guest_control.html` (`/guest`), `web/guest_guide.html` (`/guest_guide`).
- **Tập lệnh cốt lõi:** `web/house3d.js` (Three.js `r128`, nạp `web/models/smarthome_villa.glb` + 40 dây 3D), `web/js/app.js`, `web/js/mobile_app.js`, `web/js/automation_panel.js`, `web/js/wiring_guide.js`, `web/js/wokwi.js`, `web/js/voice_echo_guard.js`, `web/js/nav_auth_guard.js`.

### 2.3. Ứng Dụng Android Gốc (`app/`)
- **Cấu hình Lightbuild:** [`app/project.lightbuild.yaml`](../../app/project.lightbuild.yaml), [`app/app/lightbuild.yaml`](../../app/app/lightbuild.yaml), [`app/app-core/lightbuild.yaml`](../../app/app-core/lightbuild.yaml) (Kotlin `2.3.20`, Compose `1.10.4`, `minSdk 26`).
- **Màn hình & dữ liệu chính (`app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/`):** `MainActivity.kt`, `data/DataRepository.kt`, `ui/main/MainScreen.kt`, `MainScreenViewModel.kt`, `QrScannerScreen.kt`, `ForgotPasswordScreen.kt`, `VoiceBottomSheet.kt`, cùng 4 tab `HomeScreenTab.kt`, `DevicesScreenTab.kt`, `VoiceScreenTab.kt`, `AccountScreenTab.kt`.

### 2.4. Firmware ESP8266 & Hồ Sơ Phần Cứng (`firmware/`, `hardware/`)
- **Firmware:** [`firmware/esp8266_smarthome/esp8266_smarthome.ino`](../../firmware/esp8266_smarthome/esp8266_smarthome.ino), `offline_safety_config.h`, `offline_command_grammar.h`, `offline_fsm.h`, [`firmware/esp8266_smarthome/platformio.ini`](../../firmware/esp8266_smarthome/platformio.ini).
- **Nạp USB & Wi-Fi runtime:** [`hardware/flash_and_setup.ps1`](../../hardware/flash_and_setup.ps1).
- **SSOT Phần cứng & 3D:** [`hardware/wiring_contract.py`](../../hardware/wiring_contract.py), [`hardware/component_dimensions_ssot.py`](../../hardware/component_dimensions_ssot.py), [`hardware/wire_lengths.json`](../../hardware/wire_lengths.json), `hardware/kicad/smarthome_hub/`, `hardware/mica/`, [`hardware/in 3 d/README.md`](../../hardware/in%203%20d/README.md), `hardware/blender/`.

---

## 3. Tài Liệu Kiến Trúc Liên Quan

- [Kiến trúc hệ thống chi tiết kèm sơ đồ Mermaid (`KIEN_TRUC_HE_THONG.md`)](KIEN_TRUC_HE_THONG.md)
- [Công nghệ & phiên bản thực đo (`CONG_NGHE_VA_PHIEN_BAN.md`)](CONG_NGHE_VA_PHIEN_BAN.md)
- [Sơ đồ cơ sở dữ liệu SQLite 25 bảng (`DATABASE_SCHEMA_ERD.md`)](DATABASE_SCHEMA_ERD.md)
