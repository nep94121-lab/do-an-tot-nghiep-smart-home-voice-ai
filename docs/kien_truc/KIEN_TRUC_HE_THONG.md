# Kiến Trúc Hệ Thống Chi Tiết — Smart Home Voice AI (`v3.8.0` / `v1.0`)

Tài liệu này mô tả chi tiết kiến trúc kỹ thuật của toàn bộ các phân hệ trong **Smart Home Voice AI**, giải thích cách từng thành phần vận hành độc lập và phối hợp với nhau từ trình duyệt Web / ứng dụng Android, máy chủ trung tâm FastAPI + SQLite WAL, trợ lý giọng nói AI tiếng Việt Gemini Live cho tới vi điều khiển phần cứng NodeMCU ESP8266 v2 Amica và mạch PCB Hub DIY v3.

---

## 1. Sơ Đồ Kiến Trúc Tổng Thể Hệ Thống

```mermaid
flowchart TB
    subgraph Clients["Tầng Người Dùng (100% Tiếng Việt)"]
        WEB["Web Dashboard & 3D Digital Twin\n(HTML5/JS + Three.js r128 + /automation /auth /logs /wokwi)"]
        PWA["Mobile Web PWA (/app)\n(Service Worker + Optimistic UI)"]
        APK["Ứng dụng Android Gốc (app/)\n(Kotlin 2.3 + Jetpack Compose + Camera QR + Voice)"]
    end

    subgraph EdgeNet["Tầng Truy Cập Công Khai HTTPS"]
        VCL["Vercel Redirect (308)\ndo-an-tot-nghiep-smart-home-voice-a.vercel.app"]
        TSF["Tailscale Funnel (HTTPS)\nlaptop-6i654f8c.tail3020d6.ts.net -> 127.0.0.1:8088"]
        VCL --> TSF
    end

    subgraph Server["Máy Chủ Trung Tâm Backend (FastAPI 0.141 + Uvicorn 0.53 · Cổng 8088)"]
        API["REST API & Auth RBAC 3 Tầng\n(routes_auth, routes_devices, routes_automation, routes_guest, routes_qr, routes_logs)"]
        VOICE["Cầu Nối Giọng Nói AI (/ws)\n(Gemini Live gemini-3.8-live · Giọng Aoede · Echo Guard · Policy agyfix11)"]
        ENG["SmartHomeEngine & Automation Engine\n(Bể 1 Hẹn giờ/Lịch tuần · Bể 2 Luật IF-THEN-ELSE AND/OR & Lệnh tùy chỉnh)"]
        HUB["Realtime Hub\n(SSE /api/events & WebSocket Broadcast < 1s)"]
        DB[("SQLite 3.53.2 WAL (25 bảng 3NF)\n+ aoede_audio_cache + audit_logs")]
        MQTT["MQTT Bridge (paho-mqtt)\n8 topic smarthome/*"]
    end

    subgraph CloudAI["Dịch Vụ AI & Xác Thực Ngoài"]
        GEM["Google Gemini Live API\n(gemini-3.8-live + Aoede 24kHz PCM)"]
        SMTP["Gmail SMTP OTP\n(Xác thực 2 lớp & Quên mật khẩu)"]
    end

    subgraph Hardware["Tầng Phần Cứng IoT (PCB-Direct Hub DIY v3 · Không Breadboard)"]
        ESP["NodeMCU ESP8266 v2 Amica (CP2102)\nFirmware C++ + LittleFS /wifi_config.json + Offline FSM A1-A4"]
        ACT["6 Thiết Bị Chấp Hành\nCửa SG90 (D1) · Đèn PK (D0) · Đèn PN (D4)\nBơm Relay 1 (D6) · Còi Q1 (D8) · Loa PAM8403 Relay 2 (D7/D3)"]
        SEN["3 Cảm Biến Thực\nDHT11 (D2) · Độ ẩm đất LM393/YL-69 (A0) · Âm thanh KY-037 (D5)"]
        ESP --> ACT
        SEN --> ESP
    end

    WEB <-->|"HTTPS / WSS / SSE"| TSF
    PWA <-->|"HTTPS / WSS / SSE"| TSF
    APK <-->|"HTTPS hoặc adb reverse :8088"| TSF
    TSF <--> API
    TSF <--> VOICE
    TSF <--> HUB

    API <--> ENG
    VOICE <--> ENG
    VOICE <--> GEM
    API --> SMTP
    ENG <--> DB
    API <--> DB
    ENG --> HUB
    ENG <--> MQTT
    MQTT <-->|"MQTT & HTTP Heartbeat/Resync"| ESP
    APK -.->|"Chế độ Ngoại tuyến LAN\nPOST /offline/cmd (:80)"| ESP
```

---

## 2. Phân Tích Chi Tiết Từng Phân Hệ

### 2.1. Máy chủ Backend FastAPI & Cơ sở dữ liệu SQLite WAL (`backend/`)
- **Điểm vào chính (`backend/server.py`, API phiên bản `3.8.0`):** Khởi chạy trên `uvicorn`, phục vụ đồng thời nhóm API REST, luồng đồng bộ thời gian thực `SSE` (`GET /api/events`), WebSocket giọng nói hai chiều (`/ws`) và các trang giao diện tĩnh (`/`, `/app`, `/automation`, `/auth`, `/logs`, `/wokwi`, `/login`, `/register`, `/guest`, `/architecture`, `/archify`).
- **Phân tách Router theo nghiệp vụ (`backend/api/`):**
  - `routes_auth.py`: Đăng nhập email + mật khẩu + OTP Gmail, tạo/thu hồi phiên (`HttpOnly` cookie `sh_session_token` hoặc header `X-Session-Token`), thiết bị tin cậy (`sh_trusted_device`), đặt lại mật khẩu qua OTP, cấp vé WebSocket `/api/auth/ws_ticket`.
  - `routes_devices.py`: Điều khiển 6 thiết bị (`POST /api/device`, `/api/devices/{device_id}/control`), nhận telemetry cảm biến (`/api/dht11`, `/api/soil_moisture`, `/api/ky037`), nhịp tim mạch (`/api/hardware/heartbeat`), đồng bộ ngược sau ngoại tuyến (`/api/hardware/resync`), luồng `SSE` (`/api/events`).
  - `routes_automation.py`: Quản lý Bể 1 (hẹn giờ đếm ngược `GET /api/timers`, lịch lặp tuần `/api/schedules`) và Bể 2 (luật liên động `/api/rules`, luật tổ hợp đa cảm biến `AND`/`OR` `/api/compound_rules`, lệnh tùy chỉnh `/api/scenes`, xác nhận hành động đang chờ `/api/automation/confirm`).
  - `routes_guest.py` & `routes_qr.py`: Quản lý mã mời QR dùng một lần do Chủ nhà Cấp 1 phát hành (bảo vệ bằng mã PIN 4 chữ số băm `PBKDF2-SHA256`), đổi mã `POST /api/guest/redeem`, thu hồi tức thì.
  - `routes_logs.py`: Nhật ký kiểm toán hệ thống (`/api/logs/dashboard`), truy vấn chỉ đọc SQLite (`/api/sqlite/overview`), tri thức RAG (`/api/kb_upsert`) — chỉ dành cho Chủ nhà Cấp 1.
- **Lưu trữ bền vững SQLite 3 (`3.53.2`, chế độ `WAL`):**
  - Bật `PRAGMA journal_mode = WAL`, `PRAGMA foreign_keys = ON`, `PRAGMA synchronous = NORMAL` giúp đọc/ghi đồng thời không khóa luồng `SSE`/WebSocket.
  - Gồm **25 bảng chuẩn hóa 3NF** (chi tiết xem [`DATABASE_SCHEMA_ERD.md`](DATABASE_SCHEMA_ERD.md)): danh tính & phiên (`roles`, `users`, `sessions`, `invites`, `otp_challenges`, `trusted_devices`, `owner_pin_security`), trạng thái thiết bị (`devices`, `device_state`, `system_state_meta`), hai bể tự động hóa cách ly theo `owner_user_id` (`timers_pool`, `schedules`, `automation_rules`, `custom_commands`, `pending_confirmations`, `rules_pool`), bộ đệm âm thanh giọng đọc `aoede_audio_cache`, tri thức `knowledge_rag` và nhật ký `audit_logs`.

### 2.2. Hệ thống Phân quyền 3 Tầng (RBAC) & Mã Mời QR Dùng Một Lần
Toàn bộ quyền điều khiển được kiểm tra **bắt buộc phía máy chủ** (`backend/auth/tier_permissions.py`, `backend/auth/session_store.py`). Client không bao giờ được tự khai vai trò.

| Cấp quyền | Vai trò | Thiết bị được điều khiển | Quyền tự động hóa & Quản trị |
| :---: | :--- | :--- | :--- |
| **Cấp 1** | **Chủ nhà** (`ADMIN`) | **6/6 thiết bị:** `main_door`, `alarm_siren`, `garden_pump`, `speaker_amp`, `living_room_light`, `bedroom_light` | Toàn quyền luật/lịch toàn nhà, tạo/thu hồi mã mời QR (cần PIN Chủ nhà), duyệt thành viên, xem `/logs`, `/wokwi`, Reset hệ thống |
| **Cấp 2** | **Thành viên gia đình** (`MEMBER`) | **4/6 thiết bị:** `living_room_light`, `bedroom_light`, `garden_pump`, `speaker_amp` *(khóa Cửa chính & Còi báo động)* | Sở hữu Bể lệnh và Lịch hẹn giờ riêng cho 4 thiết bị được phép, xem `/wokwi`; **không** xem `/logs`, **không** đè lịch của Cấp 1 |
| **Cấp 3** | **Khách** (`CHILD_GUEST`) | **2/6 thiết bị:** `living_room_light`, `bedroom_light` | Điều khiển 2 đèn trên `/` hoặc `/app`, **chỉ xem** trên `/automation`; bị chặn `HTTP 403` trên `/logs` và `/wokwi` |

### 2.3. Trợ Lý Giọng Nói AI Tiếng Việt (`backend/live/`, `backend/voice/`)
- **Mô hình thời gian thực:** `gemini-3.8-live` qua WebSocket `/ws`, sử dụng **duy nhất giọng đọc tiếng Việt `Aoede`** (`24 kHz Mono 16-bit PCM`, lưu đệm câu phản hồi phổ biến trong `aoede_audio_cache`).
- **Chống vọng tiếng (Echo Guard):** `backend/live/echo_and_speech_guard.py` + `web/js/voice_echo_guard.js` lọc tiếng loa phát lại vào micro để tránh hệ thống tự nghe chính mình, đồng thời không chặn nhầm câu lệnh mới sau thông báo từ chối.
- **Chính sách giọng nói `agyfix11` (Xác nhận 1 lần & Phản hồi ngắn gọn chính xác):**
  - **Lệnh điều khiển trực tiếp & truy vấn cảm biến:** Thực thi ngay (**Actuate-First**) và trả lời tiếng Việt ngắn gọn, đúng sự thật trạng thái vật lý (ví dụ: *"Đã bật đèn phòng khách."*). Từ chối an toàn (**Fail-Closed**) nếu gọi thiết bị không nằm trong 6 thiết bị chốt (`quạt`, `điều hòa`, `TV/IR`) hoặc vượt quyền RBAC.
  - **Lệnh tùy chỉnh, hẹn giờ, lịch lặp, luật liên động & Reset:** Tạm giữ trạng thái trong `pending_confirmations` (TTL 20 giây), hỏi xác nhận **đúng 1 lần** bằng tiếng Việt; chỉ thực thi khi người dùng xác nhận (*"Có"*, *"Đồng ý"*, *"Xác nhận"*) và hủy sạch khi nói *"Không"* / *"Hủy"*.

### 2.4. Bộ Máy Tự Động Hóa 2 Bể (`backend/automation_engine.py`, `backend/engine/`)
1. **Bể 1 — Hẹn giờ đếm ngược & Lịch lặp (`timers_pool`, `schedules`):**
   - Hẹn giờ mặc định chạy **1 lần rồi tự dừng** (`repeat='once'`), hỗ trợ chu kỳ lặp (*hàng giờ*, *hàng ngày*, *hàng tuần theo thứ*, *hàng tháng*) theo múi giờ chuẩn `Asia/Saigon` (UTC+7).
   - Bảo vệ xung đột: lịch của Cấp 2 không được ghi đè hoặc hủy lịch của Chủ nhà Cấp 1.
2. **Bể 2 — Luật động, Luật tổ hợp `AND`/`OR` & Lệnh tùy chỉnh (`automation_rules`, `custom_commands`, `rules_pool`):**
   - Luật đơn `IF-THEN-ELSE` (liên động giữa thiết bị hoặc ngưỡng cảm biến, có phát hiện chu trình vô hạn bằng DFS).
   - Luật tổ hợp đa điều kiện `AND`/`OR` (ví dụ: *Nhiệt độ > 32°C `AND` Độ ẩm < 50% $\rightarrow$ Bật bơm tưới cây*) được đánh giá liên tục khi có telemetry mới.
   - Lệnh tùy chỉnh (`custom_commands`) cách ly theo `owner_user_id`, cho phép gom chuỗi thao tác dưới một câu khẩu lệnh tiếng Việt tự nhiên.

### 2.5. Web Dashboard, Bản Sao Số 3D Digital Twin & Mobile PWA (`web/`)
- **Bản sao số 3D (`web/house3d.js`, `Three.js r128`):** Nạp mô hình ngôi nhà `web/models/smarthome_villa.glb` xuất từ Blender 5.2.2, hiển thị đủ **14 module vật lý + PCB Hub DIY v3 + NodeMCU + 40 tuyến dây 3D** đọc từ `web/data/wiring_contract.json` (`breadboardUsed: false`). Khi thiết bị đổi trạng thái, cánh cửa xoay góc thực `0°–90°`, đèn sáng/tắt, bơm/còi/loa hiển thị trạng thái đồng bộ dưới `1 giây` qua `SSE`.
- **Trang hướng dẫn đấu nối PCB-Direct (`/wokwi`):** Mặc định hiển thị sơ đồ mạch 2D PCB-Direct (không breadboard), chế độ bước `1/40 .. 40/40`, bảng tìm kiếm/lọc 40 dây theo chiều dài `cm` và bảng kiểm tra tụ/diode bảo vệ `C1–C9`, `D1–D2`.
- **Giao diện di động PWA (`/app`):** Tối ưu màn hình dọc, áp dụng **Optimistic UI** kèm cửa sổ chống nháy `pendingDeviceMutations` và hỗ trợ chế độ Sáng/Tối.

### 2.6. Ứng Dụng Android Gốc (`app/`)
- Viết bằng **Kotlin 2.3.20 + Jetpack Compose 1.10.4 + Material 3 1.4.0** (`minSdk 26`, `targetSdk 34`, `compileSdk 36`), biên dịch nhanh bằng `lightbuild`.
- Gồm đầy đủ luồng người dùng thực tế: Cổng đăng nhập bắt buộc (`MainScreen`), Quên mật khẩu OTP (`ForgotPasswordScreen`), Quét mã QR mời trực tiếp bằng camera (`QrScannerScreen` $\rightarrow$ `POST /api/guest/redeem`), 4 tab chính (`HomeScreenTab`, `DevicesScreenTab`, `VoiceScreenTab` + `VoiceBottomSheet`, `AccountScreenTab`).
- Hỗ trợ chế độ trực tuyến (HTTPS Tailscale hoặc `127.0.0.1:8088` qua `adb reverse`) và dự phòng giọng nói ngoại tuyến tiếng Việt gửi thẳng tới ESP8266 qua mạng LAN (`POST /offline/cmd`).

### 2.7. Firmware ESP8266 & Cầu Nối MQTT (`firmware/`, `backend/mqtt_bridge.py`)
- **8 chủ đề MQTT chuẩn:**
  - Điều khiển & đồng bộ xuống mạch: `smarthome/cmd/actuate`, `smarthome/cmd/enroll_blink`, `smarthome/sync/pools`.
  - Telemetry & trạng thái lên máy chủ: `smarthome/telemetry/dht11`, `smarthome/telemetry/soil_moisture`, `smarthome/telemetry/sound`, `smarthome/state/report`, `smarthome/status/esp8266` (birth/LWT).
- **Dự phòng ngoại tuyến (Addendum A1–A4):** Tách thành 3 header C++ thuần (`offline_safety_config.h`, `offline_command_grammar.h`, `offline_fsm.h`) để kiểm thử độc lập trên máy tính: tự đóng & khóa cấm mở `main_door`, tự ngắt bơm sau `120s`, tự tắt còi sau `30s`, kết nối lại hàm mũ `1s..30s`, mở HTTP cục bộ cổng `80` và tự động gọi `POST /api/hardware/resync` khi mạng trở lại.

---

## 3. Các Sơ Đồ Tuần Tự Luồng Hoạt Động Chính

### 3.1. Luồng Điều Khiển Thiết Bị Thời Gian Thực (Web/App $\rightarrow$ Backend $\rightarrow$ ESP8266 $\rightarrow$ 3D Twin)

```mermaid
sequenceDiagram
    actor U as Người dùng (Web / Android)
    participant API as FastAPI (/api/device)
    participant RBAC as Session & RBAC Guard
    participant ENG as SmartHomeEngine
    participant DB as SQLite WAL
    participant MQTT as MQTT Bridge
    participant ESP as NodeMCU ESP8266
    participant HUB as SSE / WebSocket Hub

    U->>API: POST /api/device {device_id, action} + Session Cookie/Token
    API->>RBAC: Kiểm tra phiên & cấp quyền (tier <= min_tier)
    alt Không đủ quyền hoặc hết phiên
        RBAC-->>U: HTTP 401 / 403 (Tiếng Việt, giữ nguyên thiết bị)
    else Hợp lệ
        RBAC->>ENG: execute_device_action()
        ENG->>DB: Cập nhật device_state + ghi audit_logs
        ENG->>MQTT: Publish smarthome/cmd/actuate
        MQTT->>ESP: Gói tin JSON điều khiển chân GPIO tương ứng
        ESP->>ESP: Kích hoạt Servo/LED/Relay/Buzzer
        ENG->>HUB: Broadcast state_update (revision_seq++)
        HUB-->>U: Đẩy sự kiện SSE (< 1s) cập nhật UI & Nhà 3D
    end
```

### 3.2. Luồng Giọng Nói AI Tiếng Việt & Xác Nhận 1 Lần Lệnh Tùy Chỉnh (`agyfix11`)

```mermaid
sequenceDiagram
    actor U as Người dùng (Micro Web / Android)
    participant WS as FastAPI WebSocket (/ws)
    participant EG as Echo Guard & Policy (agyfix11)
    participant GEM as Gemini Live (gemini-3.8-live · Aoede)
    participant ENG as SmartHomeEngine & SQLite

    U->>WS: Luồng âm thanh PCM 16kHz ("Dạy câu 'về nhà rồi' là bật đèn phòng khách")
    WS->>EG: Kiểm tra chống vọng & quyền phiên hiện tại
    EG->>GEM: Chuyển tiếp âm thanh + danh sách công cụ theo cấp RBAC
    GEM->>WS: Tool Call: create_alias_rule / schedule_action
    WS->>ENG: Tạm giữ vào bảng pending_confirmations (TTL 20s)
    ENG-->>GEM: Trạng thái staged + câu hỏi xác nhận ngắn tiếng Việt
    GEM-->>U: Giọng Aoede 24kHz: "Bạn có xác nhận tạo lệnh 'về nhà rồi' bật đèn phòng khách không?"
    U->>WS: Trả lời: "Có, đồng ý"
    WS->>ENG: confirm_pending_action() -> Ghi vào custom_commands (theo owner_user_id)
    ENG-->>GEM: Thành công + phản hồi ngắn gọn chính xác
    GEM-->>U: Giọng Aoede 24kHz: "Đã lưu lệnh 'về nhà rồi'."
```

### 3.3. Luồng Mời Khách / Thành Viên Bằng Mã QR Dùng Một Lần

```mermaid
sequenceDiagram
    actor Owner as Chủ nhà (Cấp 1)
    actor Guest as Khách / Thành viên
    participant API as FastAPI (routes_guest / routes_qr)
    participant DB as SQLite WAL (owner_pin, invites, sessions)

    Owner->>API: POST /api/guest/invites {tier: 2|3, ttl, pin}
    API->>DB: Xác thực PIN Chủ nhà (PBKDF2-SHA256)
    API->>DB: Tạo bản ghi invites (chỉ lưu SHA-256 token_hash, dùng 1 lần)
    API-->>Owner: Trả về mã QR SVG & đường dẫn mời
    Guest->>API: Quét QR trên Android hoặc mở link -> POST /api/guest/redeem
    API->>DB: Kiểm tra chưa dùng, chưa thu hồi, còn hạn -> đánh dấu đã đổi
    API->>DB: Cấp phiên sessions đúng cấp quyền (Cấp 2 hoặc Cấp 3)
    API-->>Guest: Trả Cookie HttpOnly / X-Session-Token -> mở giao diện đúng quyền
```

### 3.4. Luồng Tự Phục Hồi Ngoại Tuyến ESP8266 (Offline Fail-Safe & Auto-Resync)

```mermaid
sequenceDiagram
    participant ESP as NodeMCU ESP8266 (Offline FSM)
    participant HW as 6 Thiết Bị + 3 Cảm Biến
    participant APK as Android LAN (/offline/cmd)
    participant SRV as Backend FastAPI (:8088)

    Note over ESP,SRV: Mất Wi-Fi / mất kết nối Backend
    ESP->>HW: Tự đóng Cửa chính (0°), khóa cấm mở (A3), nháy kép LED D0, 2 bíp ngắn D8
    ESP->>ESP: Bật máy chủ HTTP LAN :80 & SoftAP sau 15s nếu mất Wi-Fi
    APK->>ESP: POST /offline/cmd {"text": "mở cửa chính"}
    ESP-->>APK: HTTP 403 DOOR_OPEN_FORBIDDEN_OFFLINE
    APK->>ESP: POST /offline/cmd {"text": "bật đèn phòng khách"}
    ESP->>HW: Bật D0, ghi offlineDirtyMask + OfflineEventRing
    ESP-->>APK: HTTP 200 (Đã bật đèn phòng khách)
    Note over ESP,SRV: Mạng Wi-Fi & Backend khôi phục (Backoff 1s..30s)
    ESP->>SRV: POST /api/hardware/resync (trạng thái vật lý + offline_events)
    SRV->>SRV: Ghi audit_logs (board_offline_resync) & cập nhật device_state
    SRV-->>ESP: HTTP 200 OK (đồng bộ đồng nhất Web/Android)
```

---

## 4. Tài Liệu Kiến Trúc Liên Quan

- [Danh mục Công nghệ & Phiên bản chính xác (`CONG_NGHE_VA_PHIEN_BAN.md`)](CONG_NGHE_VA_PHIEN_BAN.md)
- [Sơ đồ cơ sở dữ liệu SQLite 25 bảng (`DATABASE_SCHEMA_ERD.md`)](DATABASE_SCHEMA_ERD.md)
- [Bảng phân quyền 3 cấp chốt (`docs/TIER_PERMISSIONS.md`)](../TIER_PERMISSIONS.md)
- [Bản đồ khung xương mã nguồn (`REPO_MAP.md`)](REPO_MAP.md)
- [Sơ đồ kiến trúc tương tác HTML (`smart-home-voice-ai.architecture.html`)](smart-home-voice-ai.architecture.html) *(mở qua `/architecture` hoặc `/archify` khi chạy server)*
