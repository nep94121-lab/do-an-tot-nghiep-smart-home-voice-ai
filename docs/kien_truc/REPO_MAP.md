# 🗺️ BẢN ĐỒ KHUNG XƯƠNG DỰ ÁN & MA TRẬN ẢNH HƯỞNG CHÉO (`REPO_MAP.md`)

> **QUY TẮC BẮT BUỘC CHO AI AGENT:**
> 1. **Đọc file này ĐẦU TIÊN** để lấy đúng số dòng `#Lstart-Lend` trước khi gọi `read_file` (cấm đọc cả file dài hàng nghìn dòng gây tràn Context Window).
> 2. **Trước khi sửa bất kỳ hàm, MQTT Topic hay API nào**, bắt buộc chạy lệnh kiểm tra bán kính ảnh hưởng:
>    `python -X utf8 scripts/code_graph_guard.py --impact <tên_hàm_hoặc_topic>`
> 3. **Sau khi sửa code**, bắt buộc chạy:
>    `python -X utf8 scripts/code_graph_guard.py --verify` và `python -X utf8 scripts/test_simulator_e2e.py`

---

## 1. TOP 15 HÀM TÂM CHẤN (HIGH BLAST-RADIUS — SỬA LÀ ẢNH HƯỞNG NHIỀU NƠI NHẤT)

| Hạng | Hàm / Phương thức | Vị trí (`#Lstart-Lend`) | Số nơi gọi (Callers) | Gọi xuống (Callees) | Điểm ảnh hưởng |
| :---: | :--- | :--- | :---: | :---: | :---: |
| 1 | `get_snapshot()` | [`simulator/engine/rules_pool.py#L277-L329`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L277-L329) | 30 | 5 | **95** |
| 2 | `get_auth_3layer_manager()` | [`simulator/auth_3layer.py#L1059-L1063`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L1059-L1063) | 30 | 1 | **91** |
| 3 | `emit()` | [`simulator/rule_engine.py#L153-L205`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L153-L205) | 25 | 3 | **78** |
| 4 | `append_audit_log()` | [`simulator/engine/audit_logger.py#L12-L39`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/audit_logger.py#L12-L39) | 23 | 2 | **71** |
| 5 | `get_current_user_name()` | [`simulator/engine/voice_rbac_mixin.py#L287-L291`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L287-L291) | 17 | 0 | **51** |
| 6 | `find_account()` | [`simulator/auth_3layer.py#L232-L245`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L232-L245) | 16 | 0 | **48** |
| 7 | `execute_device_action()` | [`simulator/rule_engine.py#L273-L403`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L273-L403) | 13 | 9 | **48** |
| 8 | `broadcast_rest_state_to_bridges()` | [`simulator/api/deps.py#L66-L79`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/deps.py#L66-L79) | 15 | 2 | **47** |
| 9 | `_get_user_pool()` | [`simulator/rule_engine.py#L131-L139`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L131-L139) | 14 | 0 | **42** |
| 10 | `_log_event()` | [`simulator/auth_3layer.py#L200-L230`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L200-L230) | 13 | 1 | **40** |
| 11 | `run()` | [`simulator/live/gemini_bridge.py#L838-L1054`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L838-L1054) | 6 | 21 | **39** |
| 12 | `send_ws_json()` | [`simulator/live/gemini_bridge.py#L189-L241`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L189-L241) | 12 | 2 | **38** |
| 13 | `check_duplicate_voice_gate()` | [`simulator/voice_auth.py#L1214-L1365`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1214-L1365) | 10 | 8 | **38** |
| 14 | `grant_user_permission()` | [`simulator/engine/voice_rbac_mixin.py#L648-L721`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L648-L721) | 10 | 6 | **36** |
| 15 | `_now_vn()` | [`simulator/auth/constants_and_crypto.py#L22-L23`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/constants_and_crypto.py#L22-L23) | 11 | 0 | **33** |

---

## 2. CẦU NỐI ĐỒNG BỘ LIÊN TẦNG (CROSS-LAYER CONTRACTS)

### 2.1. 19 Công cụ Gemini Live (`FunctionDeclaration` trong `server.py` <-> `rule_engine.py`)
- Danh sách: `control_device`, `schedule_action`, `update_timer`, `set_word_mapping`, `create_alias_rule`, `execute_alias_rule`, `set_if_else_rule`, `query_pools`, `query_knowledge_rag`, `request_factory_reset`, `confirm_factory_reset`, `confirm_pending_action`, `start_voice_enrollment`, `finalize_voice_enrollment`, `grant_user_permission`, `revoke_user_permission`, `set_query_permission_policy`, `admin_update_system_policy`, `admin_upsert_knowledge_rag`, `set_or_query_sensors`

### 2.2. 9 Chủ đề MQTT Chuẩn (`mqtt_bridge.py` <-> `rule_engine.py` <-> `esp8266_smarthome.ino`)
- Danh sách: `smarthome/cmd/actuate`, `smarthome/cmd/enroll_blink`, `smarthome/ir/blast`, `smarthome/ir/learn_start`, `smarthome/ir/learned_result`, `smarthome/state/report`, `smarthome/status/esp8266`, `smarthome/sync/pools`, `smarthome/telemetry/dht11`, `smarthome/telemetry/soil_moisture`

### 2.3. Các cổng HTTP REST API (`server.py` <-> `mobile_app/index.html` & `app.js`)
- Danh sách: `/`, `/api/auth3/add_family_email`, `/api/auth3/create_invite_link`, `/api/auth3/enroll_first_page_voice`, `/api/auth3/enroll_voice_sample`, `/api/auth3/family_allowlist/add`, `/api/auth3/family_emails`, `/api/auth3/forgot_password_reset`, `/api/auth3/forgot_password_send_otp`, `/api/auth3/guest/enroll_voice`, `/api/auth3/guest/handshake`, `/api/auth3/guest/verify_email`, `/api/auth3/guest_qr_complete_voice`, `/api/auth3/guest_qr_current`, `/api/auth3/guest_qr_handshake`, `/api/auth3/guest_qr_send_otp`, `/api/auth3/guest_qr_verify_otp`, `/api/auth3/invite_links`, `/api/auth3/invite_oauth_start`, `/api/auth3/invite_verify_otp`, `/api/auth3/layer1_login`, `/api/auth3/layer2_verify_otp`, `/api/auth3/layer3_voice`, `/api/auth3/overview`, `/api/auth3/qr/generate`, `/api/auth3/read_gmail_otp`, `/api/auth3/register_or_set_password`, `/api/auth3/run_test_suite`, `/api/auth3/run_tests`, `/api/auth3/send_invite_email`, `/api/auth3/voice_permission_command`, `/api/clear_audit_logs`, `/api/device`, `/api/device_control`, `/api/devices/{device_id}/control`, `/api/devops/status`, `/api/dht11`, `/api/ir_learn`, `/api/kb_upsert`, `/api/logs/append`, `/api/logs/clear`, `/api/logs/dashboard`, `/api/logs/knowledge/add`, `/api/logs/sql_query`, `/api/mobile/enroll_voice`, `/api/mobile/schedule`, `/api/server_logs_and_db`, `/api/server_mode`, `/api/soil_moisture`, `/api/sqlite/overview`, `/api/sqlite/query`, `/api/state`, `/api/text_command`, `/api/voice_auth/enroll_tier_pcm`, `/api/voice_auth/profiles`, `/api/voice_samples`, `/api/wokwi_files`, `/app`, `/archify`, `/archify/devops`, `/archify/erd`, `/auth`, `/favicon.ico`, `/guest-qr`, `/guest_enroll`, `/logs`, `/wokwi`

### 2.4. 6 Chân Phần cứng NodeMCU ESP8266 (`rule_engine.py` <-> `esp8266_smarthome.ino`)
- Danh sách: `D1`, `D2`, `D3`, `D4`, `D5`, `D6`, `D7`, `D8`

---

## 3. CHỈ MỤC HÀM & CLASS THEO TỪNG FILE (ĐỂ AI ĐỌC ĐÚNG DÒNG `#Lstart-Lend`)

### 📄 [`simulator/server.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py)
- [`L89-L95`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L89-L95) `async def disable_static_cache(request, call_next)` — *Vô hiệu hóa bộ nhớ đệm trình duyệt để phản ánh ngay lập tức thay đổi UI/Static.*
- [`L111-L112`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L111-L112) `async def index()`
- [`L116-L117`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L116-L117) `async def mobile_app_index()`
- [`L121-L122`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L121-L122) `async def wokwi_page()`
- [`L126-L127`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L126-L127) `async def logs_page()`
- [`L131-L132`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L131-L132) `async def auth_page()`
- [`L137-L138`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L137-L138) `async def guest_enroll_page()`
- [`L142-L143`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L142-L143) `async def archify_architecture_page()`
- [`L147-L148`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L147-L148) `async def archify_devops_page()`
- [`L152-L153`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L152-L153) `async def archify_erd_page()`
- [`L157-L158`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L157-L158) `async def favicon()`
- [`L163-L180`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L163-L180) `async def websocket_endpoint(websocket)` — *Tiếp nhận kết nối WebSocket từ trình duyệt Web 3D / Micro thu âm, ủy quyền sang LiveBridgeSession.*

### 📄 [`simulator/rule_engine.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py)
- [`L60-L568`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L60-L568) `class SmartHomeEngine` — *Lõi điều hành trung tâm Smart Home: tích hợp 3 Mixin (Voice RBAC, Bể 1 Timers, Bể 2 Rules) và Actuation MQTT.*
  - [`L63-L91`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L63-L91) `def __init__(on_event, on_voice_reset)`
  - [`L93-L105`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L93-L105) `def _default_overlay()`
  - [`L107-L129`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L107-L129) `def _load_overlay()`
  - [`L131-L139`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L131-L139) `def _get_user_pool(user_id)`
  - [`L141-L151`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L141-L151) `def _save_overlay()`
  - [`L153-L205`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L153-L205) `async def emit(event)`
  - [`L207-L228`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L207-L228) `def _expand_targets(device_id, action)`
  - [`L230-L236`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L230-L236) `def _state_verb_vi(dev_type, state, already)`
  - [`L238-L271`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L238-L271) `def _build_concise_spoken_reply(results)`
  - [`L273-L403`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L273-L403) `async def execute_device_action(device_id, action, source, bypass_rbac, trigger_chains)`
  - [`L405-L415`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L405-L415) `async def sync_edge_flash()` — *Đồng bộ bản sao 2 Bể (Bể 1 Hẹn giờ & Bể 2 Luật IF-ELSE) xuống Flash LittleFS của ESP8266.*
  - [`L417-L436`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L417-L436) `async def update_sensor_telemetry(temp_c, humidity_pct, wifi_rssi_dbm)` — *Cập nhật thông số cảm biến DHT11 từ mạch ESP8266 và tự động kiểm tra luật ngưỡng nhiệt độ/độ ẩm.*
  - [`L438-L475`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L438-L475) `async def update_soil_moisture_telemetry(soil_moisture_pct, auto_pump_below_pct, auto_stop_above_pct)` — *Cập nhật thông số cảm biến Độ ẩm Đất YL-69 (Chân A0) và tự động điều khiển Máy bơm tưới cây (Chân D3).*
  - [`L477-L492`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L477-L492) `async def learn_ir_remote_command(device_name, command_action, protocol, hex_code)` — *Chiếm quyền / Học lệnh Remote Hồng ngoại 38kHz (VS1838B D5 -> Lưu Write-Through -> Phát IR LED D2).*
  - [`L494-L568`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L494-L568) `async def _evaluate_reactive_if_else(changed_dev_id, new_state)` — *Kiểm tra luật IF khi `changed_dev_id` chuyển sang `new_state`.*

### 📄 [`simulator/engine/constants_and_time.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/constants_and_time.py)
- [`L21-L22`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/constants_and_time.py#L21-L22) `def get_vn_now()`
- [`L25-L27`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/constants_and_time.py#L25-L27) `def format_vn_time_ampm(dt)`
- [`L190-L197`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/constants_and_time.py#L190-L197) `def _format_clock_12h(hour_24, minute, second)`
- [`L200-L282`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/constants_and_time.py#L200-L282) `def _extract_vn_date(time_str, date_str, now_vn)` — *Tách thông tin ngày/tháng (nếu người dùng có nói rõ) ra khỏi chuỗi giờ.*
- [`L301-L324`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/constants_and_time.py#L301-L324) `def detect_repeat_mode(text, explicit_repeat)` — *Tự động nhận diện chu kỳ lặp nếu người dùng nói 'hàng ngày', 'hàng tuần', 'hàng giờ', 'hàng tháng'.*
- [`L327-L347`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/constants_and_time.py#L327-L347) `def normalize_reset_scope(raw_scope)` — *Chuẩn hóa 4 loại Reset:*
- [`L350-L437`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/constants_and_time.py#L350-L437) `def parse_vn_clock_and_date(time_str, date_str, repeat, now_vn)` — *Phân tích chuỗi giờ Việt Nam theo đúng 4 quy tắc của Sếp + chu kỳ lặp (1 lần vs hàng ngày/tuần):*
- [`L440-L446`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/constants_and_time.py#L440-L446) `def parse_vn_time_string(time_str)` — *Hàm tương thích ngược trả về (hh, mm, ss) của mốc đầu tiên.*
- [`L449-L459`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/constants_and_time.py#L449-L459) `def ensure_factory_file()` — *Mặc định gốc hoàn toàn nguyên bản: mở cửa chỉ mở cửa, bật đèn chỉ bật đèn (không có luật phụ).*

### 📄 [`simulator/engine/audit_logger.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/audit_logger.py)
- [`L12-L39`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/audit_logger.py#L12-L39) `def append_audit_log(category, event_type, summary, user_name, tier, details)` — *Ghi nhật ký bền vững (Persistent Audit Log) xuống đĩa tại simulator/data/system_audit_logs.jsonl.*
- [`L42-L58`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/audit_logger.py#L42-L58) `def read_audit_logs(limit)` — *Đọc danh sách log mới nhất từ simulator/data/system_audit_logs.jsonl.*
- [`L61-L66`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/audit_logger.py#L61-L66) `def clear_audit_logs()` — *Xóa toàn bộ log trong simulator/data/system_audit_logs.jsonl.*

### 📄 [`simulator/engine/voice_rbac_mixin.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py)
- [`L17-L773`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L17-L773) `class EngineVoiceRbacMixin` — *Mixin quản lý system_policies, kiểm tra phân quyền thiết bị theo 3 Tầng và quy trình thu âm cấp quyền giọng nói.*
  - [`L29-L66`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L29-L66) `def system_policies()`
  - [`L69-L70`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L69-L70) `def query_permission_mode()`
  - [`L72-L101`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L72-L101) `async def set_query_permission_policy(mode)` — *Thay đổi quy tắc phân quyền hỏi đáp (CHỈ Cấp 1 Nguyễn Tuấn Anh mới có quyền thay đổi).*
  - [`L103-L253`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L103-L253) `async def admin_update_system_policy(policy_key, policy_value, target_device_id)` — *Cho phép Admin Cấp 1 (Nguyễn Tuấn Anh) sửa BẤT KỲ quy tắc hệ thống, quyền hạn của Cấp 2/Cấp 3.*
  - [`L255-L264`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L255-L264) `def _init_users()`
  - [`L267-L268`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L267-L268) `def current_user_id()`
  - [`L271-L285`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L271-L285) `def current_tier()`
  - [`L287-L291`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L287-L291) `def get_current_user_name()`
  - [`L298-L337`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L298-L337) `def current_role(val)`
  - [`L339-L355`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L339-L355) `def set_active_user(user_or_role)`
  - [`L357-L371`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L357-L371) `def check_permission(required_role)`
  - [`L373-L412`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L373-L412) `def _check_custom_directive_device_lock(dev_id)`
  - [`L414-L435`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L414-L435) `def check_device_permission(dev_id)`
  - [`L437-L449`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L437-L449) `def _find_or_slug_user(target_name)`
  - [`L451-L487`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L451-L487) `async def blink_signal_light(device_id, pulse_sec)`
  - [`L489-L548`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L489-L548) `async def start_voice_enrollment(target_tier, target_name, duration_seconds, duration_sec)`
  - [`L550-L599`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L550-L599) `async def stage_voice_enrollment_analysis(f0_hz, centroid_hz, embedding, duration_sec)`
  - [`L601-L646`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L601-L646) `async def finalize_voice_enrollment(target_name, target_tier)`
  - [`L648-L721`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L648-L721) `async def grant_user_permission(target_name, target_tier, tier)`
  - [`L723-L773`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py#L723-L773) `async def revoke_user_permission(target_name)`

### 📄 [`simulator/engine/timers_pool.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/timers_pool.py)
- [`L18-L350`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/timers_pool.py#L18-L350) `class EngineTimersMixin` — *Mixin xử lý Bể 1 (Timer Pool): đặt lịch linh hoạt AM/PM/đếm ngược, sửa/hủy và chống ghi đè Tầng 1.*
  - [`L27-L46`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/timers_pool.py#L27-L46) `def _check_t1_timer_conflict(device_id, new_fire_at)` — *Kiểm tra xem cấp dưới có đặt lệnh vướng vào khung giờ hẹn giờ của Tầng 1 Nguyễn Tuấn Anh hay không.*
  - [`L48-L140`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/timers_pool.py#L48-L140) `async def schedule_timer_flexible(device_id, action, hours, minutes, seconds, vn_time_ampm, vn_date, repeat, reason)`
  - [`L142-L260`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/timers_pool.py#L142-L260) `async def schedule_action(device_id, action, delay_seconds, reason, bypass_rbac, trigger_chains, target_vn_time, repeat)`
  - [`L262-L350`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/timers_pool.py#L262-L350) `async def update_or_cancel_timer(device_id, operation, new_action, hours, minutes, seconds, vn_time_ampm, vn_date, repeat)`

### 📄 [`simulator/engine/rules_pool.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py)
- [`L21-L1112`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L21-L1112) `class EngineRulesMixin` — *Mixin quản lý Bể 2 (Rule Pool), Chế độ Offline Default, Truy vấn 2 Bể và 4 Phạm vi Reset.*
  - [`L39-L45`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L39-L45) `def get_merged_aliases(user_id)`
  - [`L47-L51`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L47-L51) `def get_word_mappings(user_id)`
  - [`L53-L57`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L53-L57) `def get_if_else_rules(user_id)`
  - [`L59-L60`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L59-L60) `def get_chains()`
  - [`L62-L74`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L62-L74) `def format_duration_vi(total_sec)`
  - [`L76-L92`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L76-L92) `def _action_device_phrase_vi(device_id, action)`
  - [`L94-L134`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L94-L134) `def describe_device_command(device_id)`
  - [`L136-L275`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L136-L275) `def get_pools_summary(query_type, target_device_id)`
  - [`L277-L329`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L277-L329) `def get_snapshot()`
  - [`L331-L381`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L331-L381) `async def set_word_mapping(custom_word, target_meaning, require_confirmation)`
  - [`L383-L456`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L383-L456) `async def create_alias_rule(phrase, target_devices_csv, target_actions_csv, require_confirmation)`
  - [`L458-L502`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L458-L502) `async def set_server_connection_mode(connected)`
  - [`L504-L636`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L504-L636) `async def execute_offline_default_command(text, source)`
  - [`L638-L680`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L638-L680) `async def execute_alias_rule(phrase)`
  - [`L682-L709`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L682-L709) `def _has_cycle(rules)`
  - [`L711-L724`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L711-L724) `def _check_t1_rule_conflict(new_rule)`
  - [`L726-L859`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L726-L859) `async def set_if_else_rule(when_device_id, when_state, then_device_id, then_action, delay_seconds, else_device_id, else_action, evaluate_now, require_confirmation)`
  - [`L861-L911`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L861-L911) `async def confirm_pending_action(confirmed)`
  - [`L913-L962`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L913-L962) `async def request_factory_reset(scope)`
  - [`L964-L985`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L964-L985) `async def confirm_factory_reset(confirmed)`
  - [`L987-L1112`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/rules_pool.py#L987-L1112) `async def factory_reset(scope)`

### 📄 [`simulator/mqtt_bridge.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py)
- [`L76-L494`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L76-L494) `class SmartHomeMQTTBridge` — *Bộ điều phối bản tin MQTT chuẩn System Design Primer:*
  - [`L84-L129`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L84-L129) `def __init__(on_event)`
  - [`L131-L141`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L131-L141) `def _load_ir_db()`
  - [`L143-L145`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L143-L145) `def _save_ir_db_write_through()` — *Write-Through Cache: Cập nhật RAM đồng thời ghi xuyên suốt xuống đĩa.*
  - [`L147-L182`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L147-L182) `async def publish(topic, payload, qos, retain, direction)` — *Phát hành gói tin MQTT với cơ chế kiểm soát Back Pressure.*
  - [`L184-L259`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L184-L259) `async def publish_actuate_command(device_id, state, action, source, user_name, tier)` — *Xuất bản tin MQTT điều khiển phần cứng ESP8266 (`smarthome/cmd/actuate`)*
  - [`L261-L276`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L261-L276) `async def publish_enrollment_blink(device_id, pulse_ms)` — *Xuất bản tin MQTT `smarthome/cmd/enroll_blink` để ESP8266 nháy đèn báo hiệu bắt đầu thu âm 3-2-1.*
  - [`L278-L329`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L278-L329) `async def sync_pools_to_esp8266_flash(timers, if_else_rules, system_policies)` — *CAP Theorem (AP Failover): Đồng bộ bản sao Bể 1 (Hẹn giờ) và Bể 2 (Luật IF-ELSE)*
  - [`L331-L358`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L331-L358) `async def update_dht11_telemetry(temp_c, humidity_pct, wifi_rssi_dbm)` — *Nhận bản tin cảm biến `smarthome/telemetry/dht11` từ chân D6 của ESP8266.*
  - [`L360-L387`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L360-L387) `async def update_soil_moisture_telemetry(soil_moisture_pct, adc_raw)` — *Nhận bản tin cảm biến Độ ẩm Đất `smarthome/telemetry/soil_moisture` từ chân A0 (YL-69 + LM393).*
  - [`L389-L413`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L389-L413) `async def start_ir_learning(device_name, command_action)` — *Bật chế độ Học lệnh chiếm quyền Remote (`smarthome/ir/learn_start`) trên chân D5 (`VS1838B`).*
  - [`L415-L479`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L415-L479) `async def complete_ir_learning(protocol, hex_code, raw_timings_us)` — *Nhận kết quả giải mã xung hồng ngoại từ ESP8266 (`smarthome/ir/learned_result`) và lưu Write-Through.*
  - [`L481-L494`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L481-L494) `def get_summary()`

### 📄 [`simulator/voice_auth.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py)
- [`L45-L176`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L45-L176) `def denoise_and_isolate_human_voice(pcm16, sr)` — *Khử tiếng ồn nền (quạt trần, điều hòa, tạp âm) và chỉ giữ lại dải tần tiếng người nói (85Hz - 3900Hz).*
- [`L179-L388`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L179-L388) `def extract_voice_features(pcm16, sr)` — *[BỘ LỌC TẦNG 1 - NHANH ~1ms]: Trích xuất tần số cơ bản F0 (Hz), Spectral Centroid (Hz),*
- [`L391-L568`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L391-L568) `def extract_stage2_deep_features(pcm16, sr)` — *[BỘ LỌC TẦNG 2 - CHUYÊN SÂU ~2.5ms]:*
- [`L571-L804`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L571-L804) `def detect_multi_speaker_and_resolve_priority(pcm16_clean, profiles, sr)` — *Phát hiện khi có 2 người cùng nói (nói nối nhau hoặc nói đè lên nhau)*
- [`L807-L814`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L807-L814) `def cosine_sim(v1, v2)`
- [`L817-L849`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L817-L849) `def transform_pcm_by_pitch_factor(pcm16, factor, sr)` — *Biến đổi cao độ (Pitch Shift) đoạn âm thanh theo hệ số `factor` (factor < 1.0 -> giọng cao hơn, factor > 1.0 -> giọng trầm hơn).*
- [`L852-L854`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L852-L854) `def transform_pcm_to_intruder_voice(pcm16, sr)` — *Biến đổi tần số giọng nói gốc thành Giọng số 2 (Giọng người lạ - Không được phép).*
- [`L857-L870`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L857-L870) `def synthesize_noisy_fan_voice(pcm16_owner, sr)` — *Tạo mẫu kiểm thử: Giọng Chủ nhà nói trong môi trường có tiếng quạt trần ù mạnh + tiếng gió nền.*
- [`L873-L888`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L873-L888) `def synthesize_two_speakers_audio(pcm16_owner, pcm16_intruder, sr)` — *Tạo mẫu kiểm thử: 2 người cùng nói trong 1 lượt (Người lạ nói chèn khúc đầu + Chủ nhà Cấp 1 nói chính).*
- [`L891-L1146`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L891-L1146) `def validate_voice_enrollment_quality(pcm16, sr)` — *Kiểm định chất lượng giọng thu âm ban đầu (First-Page Voice Enrollment Quality Gate).*
- [`L1149-L1199`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1149-L1199) `class DuplicateVoiceCheckResult` — *Kết quả kiểm tra cổng chống trùng giọng: hỗ trợ cả tuple unpacking (is_dup, reason, profile) và truy cập dict.*
  - [`L1151-L1152`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1151-L1152) `def __new__(cls, is_duplicate, reason, matched_profile)`
  - [`L1154-L1167`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1154-L1167) `def __init__(is_duplicate, reason, matched_profile)`
  - [`L1169-L1192`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1169-L1192) `def __getitem__(item)`
  - [`L1194-L1199`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1194-L1199) `def get(key, default)`
- [`L1202-L2439`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1202-L2439) `class VoiceAuthManager` — *Quản lý Xác Thực Giọng Nói Kép 2 Tầng (Bộ lọc 1 nhanh + Bộ lọc 2 sinh trắc học sâu),*
  - [`L1208-L1212`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1208-L1212) `def validate_voice_enrollment_quality(pcm16, sr)` — *Kiểm định chất lượng mẫu giọng thu âm ban đầu theo 6 tiêu chuẩn âm học.*
  - [`L1214-L1365`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1214-L1365) `def check_duplicate_voice_gate(feat_s1, deep_feat, threshold_mel, threshold_deep, f0_hz, target_tier, target_user_id)` — *Cổng Kiểm Tra Chống Trùng Giọng Trong Nhà (Duplicate Voiceprint Reject Gate):*
  - [`L1367-L1393`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1367-L1393) `def __init__(audio_dir)`
  - [`L1395-L1494`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1395-L1494) `def _init_or_load_profiles()` — *Khởi tạo hoặc nạp hồ sơ giọng nói gốc của cả 3 Cấp (Cấp 1 Chủ nhà, Cấp 2 Thành viên, Cấp 3 Khách) + Mẫu Người lạ.*
  - [`L1497-L1502`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1497-L1502) `def _write_wav16k(path, pcm16)`
  - [`L1504-L1517`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1504-L1517) `def enroll_owner_from_pcm16k(pcm_bytes, label)` — *Đăng ký vân giọng mới từ đoạn thu âm tự do 3 - 10 giây (16kHz PCM) cho Cấp 1,*
  - [`L1519-L1621`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1519-L1621) `def enroll_tier_voice_from_pcm16k(pcm_bytes, user_id, user_name, tier, role, custom_label, expires_at, check_duplicate)` — *Thu âm giọng nói thật từ Microphone (16kHz PCM) và lưu làm giọng gốc Server cho Cấp 1, Cấp 2 hoặc Cấp 3.*
  - [`L1623-L1650`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1623-L1650) `def analyze_voice_pcm16k(pcm_bytes)` — *Phân tích đoạn thu âm giọng nói 16kHz vừa thu được (đã qua lọc tiếng ồn + trích xuất 2 tầng) để cấp quyền.*
  - [`L1652-L1728`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1652-L1728) `def register_enrolled_user_profile(user_id, user_name, tier, role, f0_hz, centroid_hz, embedding, formants_hz, deep_embedding, embedding_256d)` — *Lưu hồ sơ giọng nói người dùng mới được cấp quyền (Cấp 2 hoặc Cấp 3).*
  - [`L1730-L2335`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1730-L2335) `def verify_pcm16k_and_apply_strikes(pcm_bytes, is_live_mic)` — *Quy trình Xác Thực Giọng Nói Kép 2 Tầng + Khử Tiếng Ồn + Tách 2 Người Cùng Nói:*
  - [`L2337-L2339`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L2337-L2339) `def reset_strikes()`
  - [`L2341-L2379`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L2341-L2379) `def reset_to_owner_only()` — *Reset quyền giọng nói: Xóa mọi giọng phụ khác, chỉ giữ lại duy nhất giọng của Chủ nhà (owner_voice_1) và mẫu đối chứng.*
  - [`L2381-L2390`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L2381-L2390) `def reset_to_factory_defaults()` — *Khôi phục sạch 4 hồ sơ chuẩn gốc (Chủ nhà Cấp 1, Thành viên A Cấp 2, Khách C Cấp 3, Người lạ) và xóa các bản ghi thu âm tạm thời.*
  - [`L2392-L2439`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L2392-L2439) `def verify_and_execute_voice_command(pcm_bytes, transcript_text, engine, is_live_mic)` — *Xác thực sinh trắc học giọng nói và thực thi trực tiếp câu lệnh điều khiển thiết bị trên SmartHomeEngine.*
- [`L2491-L2522`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L2491-L2522) `def parse_vietnamese_voice_command_intents(transcript_text)` — *Phân tích câu lệnh tiếng Việt của Chủ nhà thành danh sách lệnh điều khiển thiết bị SmartHomeEngine.*
- [`L2525-L2544`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L2525-L2544) `def check_duplicate_voice_gate(feat_s1, deep_feat, threshold_mel, threshold_deep, f0_hz, target_tier, target_user_id)` — *Hàm cấp module gọi trực tiếp Cổng Kiểm Tra Chống Trùng Giọng Trong Nhà.*

### 📄 [`simulator/knowledge_rag.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py)
- [`L111-L121`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L111-L121) `def ensure_kb_file()`
- [`L124-L336`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L124-L336) `class SmartHomeKnowledgeRAG` — *Bộ RAG sử dụng Google Embedding (`gemini-embedding-001`) để trả lời ngắn gọn về trợ lý ảo và quy định 3 tầng.*
  - [`L127-L132`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L127-L132) `def __init__(api_key)`
  - [`L134-L135`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L134-L135) `def _doc_text_for_embedding(item)`
  - [`L137-L177`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L137-L177) `def _load_or_build_embeddings()`
  - [`L180-L186`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L180-L186) `def _cosine(a, b)`
  - [`L188-L265`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L188-L265) `def retrieve(query, current_tier, query_permission_mode, top_k)` — *Truy xuất đoạn tri thức khớp nhất bằng Google Embedding (`gemini-embedding-001`) + Cosine Similarity.*
  - [`L267-L330`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L267-L330) `def upsert_knowledge_item(topic, content, keywords, min_tier, current_tier)` — *Cho phép Admin Cấp 1 (Nguyễn Tuấn Anh) dạy thêm hoặc sửa nội dung RAG bằng giọng nói và nhúng vector ngay.*
  - [`L332-L336`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L332-L336) `def reset_custom_knowledge()`

### 📄 [`simulator/auth_3layer.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py)
- [`L68-L1053`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L68-L1053) `class ThreeLayerAuthManager` — *Quản lý Xác thực 3 Lớp, Phân cấp Link Mời, Thu âm Trang đầu & Thu hồi quyền bằng Giọng nói.*
  - [`L75-L84`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L75-L84) `def __init__()`
  - [`L86-L119`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L86-L119) `def _normalize_account_fields(acc)`
  - [`L121-L127`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L121-L127) `def reset_to_factory_defaults()` — *Khôi phục danh sách 4 tài khoản gốc chuẩn của nhà thông minh và bảo toàn quyền Cấp 1 của Nguyễn Tuấn Anh.*
  - [`L129-L180`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L129-L180) `def _load_state()`
  - [`L182-L186`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L182-L186) `def _save_accounts()`
  - [`L188-L192`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L188-L192) `def _save_family_allowlist()`
  - [`L194-L198`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L194-L198) `def _save_invite_links()`
  - [`L200-L230`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L200-L230) `def _log_event(layer, action, email, status, detail, source, extra)`
  - [`L232-L245`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L232-L245) `def find_account(identifier)`
  - [`L250-L433`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L250-L433) `def layer1_login(email, password, login_method, source, send_gmail)` — *Lớp 1: Kiểm tra Email/Mật khẩu hoặc Google OAuth -> Kiểm tra trạng thái Quyền -> Sinh OTP Lớp 2 & gửi Gmail.*
  - [`L435-L527`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L435-L527) `def register_or_update_password(email, password, confirm_password, display_name, target_tier, source)` — *Tạo tài khoản hoặc đặt/đổi mật khẩu với bắt buộc 2 ô mật khẩu (Mật khẩu & Xác nhận lại mật khẩu).*
  - [`L529-L575`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L529-L575) `def request_password_reset_otp(email, send_gmail, source)` — *Gửi mã OTP 6 số qua Gmail khi người dùng bấm 'Quên mật khẩu'.*
  - [`L577-L603`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L577-L603) `def reset_password_with_otp(email, otp_code, new_password, confirm_password, source)` — *Xác nhận mã OTP quên mật khẩu và đặt lại mật khẩu mới (kiểm tra 2 ô mật khẩu).*
  - [`L605-L677`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L605-L677) `def upsert_speaker_account_for_voice(email, speaker_name, target_tier)` — *Đảm bảo tài khoản lưu giọng nói được khởi tạo hoặc cập nhật đúng Tên và Cấp quyền (Cấp 1 cố định là Chủ nhà).*
  - [`L679-L741`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L679-L741) `def layer2_verify_otp(email, otp_input, source)` — *Lớp 2: Xác nhận mã OTP 6 số gửi về Gmail.*
  - [`L744-L783`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L744-L783) `def analyze_pcm16k_bytes(pcm_bytes)` — *Tính tần số cơ bản F0 (Hz), năng lượng RMS và Spectral Centroid từ luồng PCM 16-bit 16kHz gửi từ Điện thoại/Web.*
  - [`L785-L1053`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L785-L1053) `def recognize_or_enroll_voice_from_device(mode, pcm16k_b64, measured_f0_hz, email, target_name, target_tier, password, source_device)` — *Lớp 3: Nhận bản thu âm giọng nói từ Điện thoại hoặc Web đẩy lên Server.*
- [`L1059-L1063`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L1059-L1063) `def get_auth_3layer_manager()`
- [`L1069-L1087`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth_3layer.py#L1069-L1087) `def check_duplicate_voice_gate(feat_s1, deep_feat, threshold_mel, threshold_deep, f0_hz, target_tier, target_user_id)` — *Hàm cấp module gọi trực tiếp Cổng Kiểm Tra Chống Trùng Giọng Trong Nhà.*

### 📄 [`simulator/auth/constants_and_crypto.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/constants_and_crypto.py)
- [`L22-L23`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/constants_and_crypto.py#L22-L23) `def _now_vn()`
- [`L26-L33`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/constants_and_crypto.py#L26-L33) `def hash_password(password, salt)`
- [`L36-L38`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/constants_and_crypto.py#L36-L38) `def verify_password_hash(password, expected_hash, salt)`
- [`L41-L46`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/constants_and_crypto.py#L41-L46) `def build_reading_prompt(display_name, tier)`
- [`L241-L282`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/constants_and_crypto.py#L241-L282) `def validate_dns_mx_record(email)` — *Kiểm tra định dạng email theo RFC 5322 và kiểm tra bản ghi DNS MX thực tế của tên miền.*

### 📄 [`simulator/auth/invite_and_gmail_mixin.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py)
- [`L24-L1139`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L24-L1139) `class AuthInviteGmailMixin` — *Mixin xử lý Email Allowlist, Phân cấp Link Mời, Google OAuth + Gmail OTP, Thu âm Trang đầu và Xóa/Bật quyền bằng giọng nói.*
  - [`L32-L203`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L32-L203) `def add_family_email(actor_id, target_email, target_tier, source)` — *Thêm Email Gia Đình (Email Allowlist) theo phân quyền 3 tầng.*
  - [`L205-L207`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L205-L207) `def get_family_email_allowlist()` — *Trả về toàn bộ danh sách Email Gia Đình đã được cấp quyền.*
  - [`L209-L230`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L209-L230) `def check_duplicate_voice_gate(feat_s1, deep_feat, threshold_mel, threshold_deep, f0_hz, target_tier, target_user_id)` — *Cổng Kiểm Tra Chống Trùng Giọng Trong Nhà (ủy quyền trực tiếp tới VoiceAuthManager).*
  - [`L232-L349`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L232-L349) `def validate_and_enroll_voice(email, pcm_bytes, source_device, check_duplicate)` — *Kiểm định chất lượng âm thanh, kiểm tra chống trùng giọng trong nhà và lưu hồ sơ giọng chính.*
  - [`L351-L414`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L351-L414) `def get_invite_links_for_account(issuer_identifier)` — *Trả về các đường link mời mà tài khoản hiện tại được phép gửi xuống cấp dưới.*
  - [`L416-L499`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L416-L499) `def create_custom_invite_link(issuer_identifier, target_tier, source)` — *Kiểm tra chặt chẽ phân quyền tạo link mời.*
  - [`L501-L574`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L501-L574) `def send_invite_link_via_gmail(invite_code, recipient_email, source)` — *Gửi trực tiếp đường Link Mời đăng ký xuống Gmail của người cấp dưới qua `gws gmail`.*
  - [`L576-L667`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L576-L667) `def send_real_gmail_otp(target_email, otp_code, display_name, issued_password, invite_info)` — *Gửi email OTP 6 số (kèm mật khẩu cấp phát nếu đăng ký qua link mời) thật 100% qua `gws gmail`.*
  - [`L669-L734`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L669-L734) `def read_latest_otp_from_gmail_inbox(message_id)` — *Tự động vào hộp thư Gmail thật (`nep94121@gmail.com`) qua `gws gmail` để đọc thư vừa gửi và trích xuất mã OTP 6 số.*
  - [`L736-L814`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L736-L814) `def start_invite_oauth_registration(invite_code, google_email, display_name, custom_password, send_gmail, source)` — *Khi cấp dưới bấm vào đường link mời (`/auth?invite=...`) và chọn Đăng nhập bằng Google OAuth (Gmail).*
  - [`L816-L929`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L816-L929) `def verify_invite_otp_and_create_account(email, otp_input, source)` — *Xác nhận mã OTP gửi về Gmail khi đăng ký qua Link mời -> Kích hoạt tài khoản.*
  - [`L931-L983`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L931-L983) `def complete_first_page_voice_enrollment(email, spoken_text, pcm16k_b64, measured_f0_hz, hold_duration_sec, source_device)` — *Khi người dùng mới vào Trang Đầu, đọc dòng chữ mẫu hiển thị trên màn hình và giữ nút thu âm.*
  - [`L985-L1069`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L985-L1069) `def set_account_permission_by_voice_or_admin(target_identifier, enable_permission, actor_tier, spoken_command, source_device)` — *Xử lý khi Chủ nhà (Cấp 1) ra lệnh bằng giọng nói ở nhà để xóa cấp quyền hoặc bật lại quyền.*
  - [`L1071-L1139`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/invite_and_gmail_mixin.py#L1071-L1139) `def parse_and_execute_voice_permission_command(spoken_text, actor_tier, source_device)` — *Nhận diện tự nhiên câu nói xóa quyền / bật lại quyền của Chủ nhà trên thiết bị.*

### 📄 [`simulator/auth/qr_totp_mixin.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/qr_totp_mixin.py)
- [`L18-L289`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/qr_totp_mixin.py#L18-L289) `class AuthQrTotpMixin` — *Mixin xử lý QR Động 10 giây (TOTP), Single-Use Handshake và xác thực Email OTP kèm DNS MX.*
  - [`L26-L87`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/qr_totp_mixin.py#L26-L87) `def generate_dynamic_qr_token(issuer_tier, duration_type, host_url)` — *Sinh mã QR Động xoay vòng mỗi 10 giây (TOTP HMAC-SHA256) kèm giới hạn thời hạn cho Khách Cấp 3.*
  - [`L89-L197`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/qr_totp_mixin.py#L89-L197) `def consume_guest_handshake(token, target_window, used_token_store, duration_type)` — *Xác thực mã QR 10s khi khách quét mã mở trang thu âm (Single-Use Token + 15-min Guest Session).*
  - [`L199-L201`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/qr_totp_mixin.py#L199-L201) `def validate_dns_mx_record(email)` — *Kiểm tra định dạng email và bản ghi DNS MX thực tế của tên miền.*
  - [`L203-L289`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/qr_totp_mixin.py#L203-L289) `def send_and_verify_email_otp(email, confirm_email, input_otp, otp_code, session_id, store, send_gmail)` — *Xác thực Email tùy chọn của khách với 2 ô nhập khớp 100%, kiểm tra DNS MX và gửi/xác nhận mã OTP.*

### 📄 [`simulator/auth/test_suite_mixin.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/test_suite_mixin.py)
- [`L10-L334`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/test_suite_mixin.py#L10-L334) `class AuthTestSuiteMixin` — *Mixin thực thi 14 kịch bản kiểm thử tự động 3 lớp và tổng hợp trạng thái tài khoản (`get_overview`).*
  - [`L21-L272`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/test_suite_mixin.py#L21-L272) `def run_automated_3layer_test_suite(send_real_email_on_test1)` — *Chạy bảng kiểm thử tự động toàn diện 14 kịch bản (TEST-01 -> TEST-14).*
  - [`L274-L334`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/auth/test_suite_mixin.py#L274-L334) `def get_overview(active_email)`

### 📄 [`simulator/database_sqlite.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/database_sqlite.py)
- [`L138-L140`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/database_sqlite.py#L138-L140) `def _now_iso()`
- [`L143-L148`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/database_sqlite.py#L143-L148) `def get_connection()`
- [`L158-L168`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/database_sqlite.py#L158-L168) `def init_sqlite_database()` — *Khởi tạo cấu trúc 8 bảng SQL chuẩn 3NF + Indexes và nạp dữ liệu ban đầu nếu bảng rỗng.*
- [`L171-L204`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/database_sqlite.py#L171-L204) `def insert_audit_log_sqlite(entry, user_id)` — *Ghi trực tiếp 1 bản ghi nhật ký vào bảng `audit_logs` trong SQLite (ACID Transaction).*
- [`L207-L234`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/database_sqlite.py#L207-L234) `def clear_audit_logs_sqlite()` — *Xóa sạch bảng audit_logs trong SQLite và chèn lại 1 bản ghi logs_cleared.*
- [`L237-L591`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/database_sqlite.py#L237-L591) `def sync_engine_state_to_sqlite(engine)` — *Đồng bộ toàn bộ trạng thái từ SmartHomeEngine + Voiceprints + Knowledge RAG + IR DB vào 8 bảng SQLite.*
- [`L594-L660`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/database_sqlite.py#L594-L660) `def get_sqlite_overview()` — *Trả về thông tin chi tiết 8 bảng SQLite (`smarthome.db`), cấu hình WAL/FK, số dòng và dữ liệu mẫu.*
- [`L669-L705`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/database_sqlite.py#L669-L705) `def execute_readonly_sql(sql_query, limit)` — *Thực thi truy vấn SQL chỉ đọc (SELECT / PRAGMA / EXPLAIN) an toàn trên `smarthome.db`.*

### 📄 [`simulator/voice/biometrics_neural.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice/biometrics_neural.py)
- [`L25-L150`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice/biometrics_neural.py#L25-L150) `def extract_neural_embedding_256d(pcm_16k_mono, sr)` — *Trích xuất vector đặc trưng sinh trắc học 256 chiều bất biến theo cao độ pitch F0.*
- [`L153-L164`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice/biometrics_neural.py#L153-L164) `def compute_neural_similarity(emb1, emb2)` — *Tính độ tương đồng Cosine giữa 2 vector Neural Embedding 256 chiều.*
- [`L167-L236`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice/biometrics_neural.py#L167-L236) `def check_duplicate_voice_gate(pcm_16k_mono, target_tier, exclude_user_id, profiles)` — *Cổng So Khớp Trùng Giọng Sinh Trắc Học Trong Nhà (Duplicate Voiceprint Reject Gate).*
- [`L239-L301`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice/biometrics_neural.py#L239-L301) `def verify_speaker_identity_256d(pcm_16k_mono, profiles)` — *Xác thực danh tính người nói qua mô hình 256 chiều.*

### 📄 [`simulator/voice/vad_vietnamese.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice/vad_vietnamese.py)
- [`L15-L106`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice/vad_vietnamese.py#L15-L106) `def is_vietnamese_speech(pcm_bytes, sr)` — *Phân tích cấu trúc âm thanh xem có phải là giọng nói tiếng Việt hợp lệ hay không.*
- [`L109-L130`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice/vad_vietnamese.py#L109-L130) `class VietnameseVADStreamFilter` — *Bộ lọc VAD Streaming hỗ trợ kiểm tra thời gian thực từng chunk âm thanh.*
  - [`L112-L115`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice/vad_vietnamese.py#L112-L115) `def __init__(sample_rate, window_ms)`
  - [`L117-L127`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice/vad_vietnamese.py#L117-L127) `def process_chunk(chunk_pcm)` — *Xử lý chunk âm thanh đến. Trả về (is_speech, reason).*
  - [`L129-L130`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice/vad_vietnamese.py#L129-L130) `def reset()`
- [`L133-L139`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice/vad_vietnamese.py#L133-L139) `def validate_voice_enrollment_quality(pcm16, sr)` — *Kiểm định chất lượng âm thanh thu âm phục vụ đăng ký sinh trắc học.*

### 📄 [`simulator/voice/denoiser.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice/denoiser.py)
- [`L18-L155`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice/denoiser.py#L18-L155) `def denoise_and_isolate_human_voice(pcm16, sr)` — *Khử tiếng ồn nền (quạt trần, điều hòa, tạp âm) và chỉ giữ lại dải tần tiếng người nói (85Hz - 3900Hz).*

### 📄 [`simulator/live/gemini_bridge.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py)
- [`L86-L127`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L86-L127) `def _sanitize_vietnamese_input_transcript(raw_text, tools_called)` — *Làm sạch văn bản phiên âm đầu vào từ Gemini Live.*
- [`L130-L1066`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L130-L1066) `class LiveBridgeSession` — *Quản lý kết nối giữa 1 client WebSocket và phiên Gemini 3.8 Live.*
  - [`L133-L187`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L133-L187) `def __init__(ws, websocket, engine, voice_auth, knowledge_rag)`
  - [`L189-L241`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L189-L241) `async def send_ws_json(payload)`
  - [`L243-L249`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L243-L249) `def _reset_turn_metrics(anchor_ts)`
  - [`L251-L276`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L251-L276) `async def _sync_rules_context_to_gemini(event_note, send_to_model)`
  - [`L278-L364`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L278-L364) `async def _apply_voice_tier_and_sync(auth_res, sample_id, label)`
  - [`L366-L462`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L366-L462) `async def _ensure_current_mic_utterance_verified()` — *Kiểm tra giọng nói của câu đang nói qua Mic đúng 1 lần duy nhất trước khi cho phép bất kỳ tool_call hoặc âm thanh AI nào phát ra.*
  - [`L464-L623`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L464-L623) `async def gemini_receive_loop()` — *Zero-Drop Reconnect Loop: Duy trì kết nối liên tục tới Gemini 3.8 Live.*
  - [`L625-L777`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L625-L777) `async def stream_wav_sample(sample_id)`
  - [`L779-L798`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L779-L798) `async def _flush_mic_silence_to_gemini()`
  - [`L800-L836`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L800-L836) `async def handle_mic_chunk(pcm_bytes, is_sp)`
  - [`L838-L1054`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L838-L1054) `async def run()`
  - [`L1056-L1066`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/gemini_bridge.py#L1056-L1066) `async def _periodic_timer_sync()`

### 📄 [`simulator/live/tool_dispatcher_mixin.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/tool_dispatcher_mixin.py)
- [`L18-L476`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/tool_dispatcher_mixin.py#L18-L476) `class LiveToolDispatcherMixin` — *Mixin xử lý luồng thu âm cấp quyền giọng nói và thực thi các Function Calls từ Gemini Live.*
  - [`L28-L54`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/tool_dispatcher_mixin.py#L28-L54) `async def _run_voice_enrollment_sequence(duration_seconds, target_tier, target_name)`
  - [`L56-L147`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/tool_dispatcher_mixin.py#L56-L147) `async def _process_completed_voice_enrollment(pcm_bytes)`
  - [`L149-L476`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/tool_dispatcher_mixin.py#L149-L476) `async def handle_tool_call(fc)`

### 📄 [`simulator/live/prompt_builder.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/prompt_builder.py)
- [`L615-L729`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/prompt_builder.py#L615-L729) `def build_system_instruction(engine)`
- [`L732-L752`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/prompt_builder.py#L732-L752) `def make_live_config(engine)`

### 📄 [`simulator/live/tts_rejection_vi.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/tts_rejection_vi.py)
- [`L35-L86`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/tts_rejection_vi.py#L35-L86) `def _generate_vietnamese_speech_pcm24k(text, sr)` — *Tạo mẫu âm thanh giọng nữ tiếng Việt 24kHz tự nhiên (F0 ~ 215Hz, Formant Resonators).*
- [`L89-L94`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/tts_rejection_vi.py#L89-L94) `def _init_precache()` — *Khởi tạo toàn bộ các câu từ chối chuẩn vào RAM khi server nạp module.*
- [`L101-L118`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/tts_rejection_vi.py#L101-L118) `def synthesize_vi_rejection_audio_24k(reason_code)` — *Trả về dữ liệu âm thanh 24kHz Mono 16-bit PCM cho mã lý do từ chối.*
- [`L121-L129`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/tts_rejection_vi.py#L121-L129) `def get_rejection_audio_b64(reason_code)` — *Trả về chuỗi base64 của âm thanh từ chối 24kHz PCM để gửi qua WebSocket.*
- [`L132-L134`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/live/tts_rejection_vi.py#L132-L134) `def get_rejection_speech_text(reason_code)` — *Trả về nội dung văn bản tiếng Việt của câu từ chối.*

### 📄 [`simulator/api/deps.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/deps.py)
- [`L30-L36`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/deps.py#L30-L36) `async def _emit_to_all_active_bridges(event)` — *Phát sự kiện trực tiếp từ _REST_ENGINE tới toàn bộ các kết nối WebSocket đang hoạt động.*
- [`L46-L48`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/deps.py#L46-L48) `def get_knowledge_rag()` — *Trả về Singleton kho tri thức RAG.*
- [`L51-L53`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/deps.py#L51-L53) `def get_rest_engine()` — *Trả về Singleton engine quản trị thiết bị và luật.*
- [`L56-L58`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/deps.py#L56-L58) `def get_boot_voice_auth()` — *Trả về Singleton quản trị sinh trắc học giọng nói.*
- [`L61-L63`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/deps.py#L61-L63) `def get_active_bridges()` — *Trả về danh sách các phiên kết nối WebSocket Gemini Live đang hoạt động.*
- [`L66-L79`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/deps.py#L66-L79) `async def broadcast_rest_state_to_bridges()` — *Đồng bộ trạng thái REST Engine sang toàn bộ các kết nối WebSocket đang hoạt động.*
- [`L86-L93`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/deps.py#L86-L93) `def load_key()` — *Đọc GEMINI_API_KEY từ .env hoặc biến môi trường.*
- [`L99-L104`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/deps.py#L99-L104) `def safe_str(msg)` — *Che key nếu xuất hiện trong log hoặc thông báo lỗi.*

### 📄 [`simulator/api/routes_devices.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_devices.py)
- [`L36-L38`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_devices.py#L36-L38) `async def api_get_state()` — *Trả về toàn bộ snapshot trạng thái thiết bị, cảm biến và luật hiện tại.*
- [`L43-L61`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_devices.py#L43-L61) `async def api_control_device(payload)` — *Điều khiển bật/tắt hoặc mở/đóng thiết bị từ App Mobile hoặc Web.*
- [`L65-L69`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_devices.py#L65-L69) `async def api_control_device_by_path(device_id, payload)` — *Điều khiển bật/tắt thiết bị theo đường dẫn REST /api/devices/{device_id}/control.*
- [`L73-L94`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_devices.py#L73-L94) `async def api_mobile_schedule(payload)` — *Tạo hẹn giờ từ ứng dụng di động Android.*
- [`L98-L104`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_devices.py#L98-L104) `async def api_ir_learn(payload)` — *Học lệnh điều khiển hồng ngoại IR từ xa.*
- [`L108-L115`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_devices.py#L108-L115) `async def api_update_dht11(payload)` — *Cập nhật thông số cảm biến nhiệt độ & độ ẩm không khí DHT11 (chân D6).*
- [`L119-L124`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_devices.py#L119-L124) `async def api_update_soil_moisture(payload)` — *Cập nhật cảm biến độ ẩm đất YL-69 (A0) và tự động bật/tắt bơm vườn.*
- [`L128-L138`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_devices.py#L128-L138) `async def api_set_server_mode(payload)` — *Chuyển đổi chế độ Online Gemini Live <-> Offline Mạch độc lập.*
- [`L142-L216`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_devices.py#L142-L216) `async def api_text_command(payload)` — *Xử lý khẩu lệnh dạng text, hỗ trợ offline command, cảm biến, alias và phân quyền.*
- [`L220-L231`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_devices.py#L220-L231) `async def api_get_wokwi_files()` — *Trả về sơ đồ Wokwi diagram.json và code Arduino esp8266_smarthome.ino.*

### 📄 [`simulator/api/routes_auth.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py)
- [`L36-L38`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L36-L38) `async def api_auth3_overview(email)` — *Tổng quan trạng thái phân quyền và tài khoản.*
- [`L42-L44`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L42-L44) `async def api_auth3_invite_links(email)` — *Danh sách link mời còn hiệu lực.*
- [`L48-L57`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L48-L57) `async def api_auth3_send_invite_email(payload)` — *Gửi link mời qua Gmail thực tế.*
- [`L61-L79`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L61-L79) `async def api_auth3_create_invite_link(payload)` — *Tạo link mời theo phân quyền.*
- [`L84-L118`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L84-L118) `async def api_auth3_add_family_email(payload)` — *Thêm email vào allowlist gia đình (Hỗ trợ alias chống 404).*
- [`L122-L127`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L122-L127) `async def api_auth3_family_emails()` — *Danh sách email gia đình trong allowlist.*
- [`L131-L155`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L131-L155) `async def api_auth3_invite_oauth_start(payload)` — *Đăng ký qua link mời và Google OAuth.*
- [`L159-L181`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L159-L181) `async def api_auth3_invite_verify_otp(payload)` — *Xác nhận mã OTP từ link mời và tạo tài khoản.*
- [`L185-L189`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L185-L189) `async def api_auth3_read_gmail_otp(payload)` — *Đọc mã OTP mới nhất từ hộp thư Gmail qua công cụ gws.*
- [`L193-L280`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L193-L280) `async def api_auth3_enroll_first_page_voice(payload)` — *Thu âm giọng nói câu mẫu trang đầu.*
- [`L284-L388`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L284-L388) `async def api_auth3_enroll_voice_sample(payload)` — *Kiểm định chất lượng và thu âm mẫu giọng chính.*
- [`L392-L419`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L392-L419) `async def api_mobile_enroll_voice(payload)` — *Thu âm & đăng ký mẫu giọng từ App Android.*
- [`L423-L430`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L423-L430) `async def api_voice_auth_profiles()` — *Danh sách hồ sơ giọng nói gốc trên Server.*
- [`L434-L473`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L434-L473) `async def api_voice_auth_enroll_tier_pcm(payload)` — *Thu âm giọng nói thật 16kHz PCM từ mic lưu làm profile server.*
- [`L477-L523`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L477-L523) `async def api_auth3_voice_permission_command(payload)` — *Khẩu lệnh phân quyền hoặc thu hồi quyền bằng giọng nói.*
- [`L527-L549`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L527-L549) `async def api_auth3_layer1_login(payload)` — *Xác thực Lớp 1 (Mật khẩu PBKDF2 hoặc PIN).*
- [`L553-L567`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L553-L567) `async def api_auth3_layer2_verify_otp(payload)` — *Xác thực Lớp 2 (Mã OTP 6 số).*
- [`L571-L594`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L571-L594) `async def api_auth3_register_or_set_password(payload)` — *Tạo tài khoản hoặc đặt/đổi mật khẩu với 2 ô mật khẩu xác nhận.*
- [`L598-L608`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L598-L608) `async def api_auth3_forgot_password_send_otp(payload)` — *Gửi mã OTP 6 số về Gmail cho tính năng Quên mật khẩu.*
- [`L612-L626`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L612-L626) `async def api_auth3_forgot_password_reset(payload)` — *Xác nhận OTP quên mật khẩu và đặt lại mật khẩu mới (kiểm tra 2 ô mật khẩu).*
- [`L630-L666`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L630-L666) `async def api_auth3_layer3_voice(payload)` — *Xác thực Lớp 3 (Sinh trắc học giọng nói).*
- [`L671-L687`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L671-L687) `async def api_auth3_run_tests(payload)` — *Chạy bộ kiểm thử tự động 14 ca xác thực 3 tầng (Hỗ trợ alias chống 404).*
- [`L691-L700`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py#L691-L700) `async def api_list_voice_samples()` — *Danh sách các file âm thanh wav mẫu trong test_audio/.*

### 📄 [`simulator/api/routes_qr.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_qr.py)
- [`L48-L66`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_qr.py#L48-L66) `def generate_qr_svg_string(content)` — *Sinh chuỗi SVG QR code chuẩn từ chuỗi nội dung content.*
- [`L72-L157`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_qr.py#L72-L157) `async def api_auth3_guest_qr_current(payload, duration, duration_type, dur, host, host_url, issuer_tier, target_tier, tier)` — *Sinh mã QR Động xoay vòng mỗi 10 giây (TOTP 10s) kèm SVG QR thực tế cho Khách (Cấp 3) hoặc Gia đình (Cấp 2).*
- [`L162-L206`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_qr.py#L162-L206) `async def api_auth3_guest_qr_handshake(payload)` — *Bắt tay xác thực mã QR 10 giây khi khách quét mã mở trang thu âm /guest_enroll.*
- [`L211-L372`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_qr.py#L211-L372) `async def api_auth3_guest_qr_complete_voice(payload)` — *Tiếp nhận bản thu âm PCM 16kHz của khách / thành viên trên trang /guest_enroll.*
- [`L376-L441`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_qr.py#L376-L441) `async def api_auth3_guest_qr_send_otp(payload)` — *Gửi OTP xác thực email khách sau khi kiểm tra so khớp 2 ô và kiểm tra DNS MX thực tế.*
- [`L446-L530`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_qr.py#L446-L530) `async def api_auth3_guest_qr_verify_otp(payload)` — *Xác nhận mã OTP email của khách và kích hoạt tài khoản khách.*

### 📄 [`simulator/api/routes_logs.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_logs.py)
- [`L58-L65`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_logs.py#L58-L65) `def _safe_json(filename)`
- [`L70-L201`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_logs.py#L70-L201) `async def api_logs_dashboard(category, q)` — *Cung cấp dữ liệu toàn diện cho trang Quản trị Nhật ký (/logs) và Mobile Dashboard.*
- [`L206-L214`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_logs.py#L206-L214) `async def api_logs_sql_query(payload)` — *Thực thi câu lệnh SQL chỉ đọc (SELECT, PRAGMA, EXPLAIN) an toàn trên smarthome.db.*
- [`L219-L244`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_logs.py#L219-L244) `async def api_logs_knowledge_add(payload)` — *Thêm hoặc cập nhật tri thức RAG vào knowledge_base.json và bảng knowledge_rag của SQLite.*
- [`L248-L263`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_logs.py#L248-L263) `async def api_logs_append(payload)` — *Tiếp nhận bản ghi log thủ công từ client hoặc demo event ghi bền vững.*
- [`L268-L279`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_logs.py#L268-L279) `async def api_logs_clear()` — *Làm sạch nhật ký kiểm toán hệ thống theo lệnh của Quản trị viên Cấp 1.*
- [`L283-L285`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_logs.py#L283-L285) `async def api_sqlite_overview()` — *Trả về tổng quan 8 bảng CSDL SQLite smarthome.db.*
- [`L289-L297`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_logs.py#L289-L297) `async def api_devops_status()` — *Trả về biên lai DevOps 5 cổng và trạng thái CI/CD.*

