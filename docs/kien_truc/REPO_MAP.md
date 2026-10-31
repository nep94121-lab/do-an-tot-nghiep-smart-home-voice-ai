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
| 1 | `get_snapshot()` | [`simulator/rule_engine.py#L1138-L1190`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1138-L1190) | 28 | 5 | **89** |
| 2 | `emit()` | [`simulator/rule_engine.py#L887-L889`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L887-L889) | 25 | 0 | **75** |
| 3 | `execute_device_action()` | [`simulator/rule_engine.py#L1693-L1830`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1693-L1830) | 12 | 9 | **45** |
| 4 | `_get_user_pool()` | [`simulator/rule_engine.py#L868-L876`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L868-L876) | 14 | 0 | **42** |
| 5 | `get_current_user_name()` | [`simulator/rule_engine.py#L770-L774`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L770-L774) | 14 | 0 | **42** |
| 6 | `_save_overlay()` | [`simulator/rule_engine.py#L878-L885`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L878-L885) | 10 | 1 | **31** |
| 7 | `send_ws_json()` | [`simulator/server.py#L945-L960`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L945-L960) | 9 | 0 | **27** |
| 8 | `_broadcast_rest_state_to_bridges()` | [`simulator/server.py#L779-L791`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L779-L791) | 8 | 2 | **26** |
| 9 | `handle_tool_call()` | [`simulator/server.py#L1102-L1351`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1102-L1351) | 1 | 23 | **26** |
| 10 | `run()` | [`simulator/server.py#L1616-L1799`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1616-L1799) | 1 | 20 | **23** |
| 11 | `publish()` | [`simulator/mqtt_bridge.py#L145-L180`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L145-L180) | 7 | 0 | **21** |
| 12 | `factory_reset()` | [`simulator/rule_engine.py#L2999-L3130`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2999-L3130) | 4 | 7 | **19** |
| 13 | `get_if_else_rules()` | [`simulator/rule_engine.py#L906-L910`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L906-L910) | 5 | 1 | **16** |
| 14 | `check_permission()` | [`simulator/rule_engine.py#L1192-L1206`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1192-L1206) | 5 | 1 | **16** |
| 15 | `get_merged_aliases()` | [`simulator/rule_engine.py#L891-L898`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L891-L898) | 5 | 1 | **16** |

---

## 2. CẦU NỐI ĐỒNG BỘ LIÊN TẦNG (CROSS-LAYER CONTRACTS)

### 2.1. 19 Công cụ Gemini Live (`FunctionDeclaration` trong `server.py` <-> `rule_engine.py`)
- Danh sách: `control_device`, `schedule_action`, `update_timer`, `set_word_mapping`, `create_alias_rule`, `execute_alias_rule`, `set_if_else_rule`, `query_pools`, `query_knowledge_rag`, `request_factory_reset`, `confirm_factory_reset`, `confirm_pending_action`, `start_voice_enrollment`, `finalize_voice_enrollment`, `grant_user_permission`, `revoke_user_permission`, `set_query_permission_policy`, `admin_update_system_policy`, `admin_upsert_knowledge_rag`

### 2.2. 9 Chủ đề MQTT Chuẩn (`mqtt_bridge.py` <-> `rule_engine.py` <-> `esp8266_smarthome.ino`)
- Danh sách: `smarthome/cmd/actuate`, `smarthome/cmd/enroll_blink`, `smarthome/ir/blast`, `smarthome/ir/learn_start`, `smarthome/ir/learned_result`, `smarthome/state/report`, `smarthome/status/esp8266`, `smarthome/sync/pools`, `smarthome/telemetry/dht11`, `smarthome/telemetry/soil_moisture`

### 2.3. Các cổng HTTP REST API (`server.py` <-> `mobile_app/index.html` & `app.js`)
- Danh sách: `/`, `/api/device`, `/api/dht11`, `/api/ir_learn`, `/api/server_mode`, `/api/soil_moisture`, `/api/state`, `/api/text_command`, `/api/voice_samples`, `/api/wokwi_files`, `/app`, `/wokwi`

### 2.4. 6 Chân Phần cứng NodeMCU ESP8266 (`rule_engine.py` <-> `esp8266_smarthome.ino`)
- Danh sách: `D1`, `D2`, `D3`, `D5`, `D6`, `D7`, `D8`

---

## 3. CHỈ MỤC HÀM & CLASS THEO TỪNG FILE (ĐỂ AI ĐỌC ĐÚNG DÒNG `#Lstart-Lend`)

### 📄 [`simulator/server.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py)
- [`L45-L49`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L45-L49) `def get_knowledge_rag()`
- [`L69-L75`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L69-L75) `def load_key()`
- [`L81-L82`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L81-L82) `def safe_str(msg)`
- [`L651-L753`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L651-L753) `def build_system_instruction(engine)`
- [`L756-L768`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L756-L768) `def make_live_config(engine)`
- [`L779-L791`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L779-L791) `async def _broadcast_rest_state_to_bridges()`
- [`L795-L796`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L795-L796) `async def index()`
- [`L800-L801`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L800-L801) `async def mobile_app_index()`
- [`L805-L806`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L805-L806) `async def wokwi_page()`
- [`L810-L814`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L810-L814) `async def api_get_wokwi_files()`
- [`L818-L819`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L818-L819) `async def api_get_state()`
- [`L823-L828`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L823-L828) `async def api_control_device(payload)`
- [`L832-L837`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L832-L837) `async def api_ir_learn(payload)`
- [`L841-L847`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L841-L847) `async def api_update_dht11(payload)`
- [`L851-L855`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L851-L855) `async def api_update_soil_moisture(payload)`
- [`L859-L868`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L859-L868) `async def api_set_server_mode(payload)`
- [`L872-L901`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L872-L901) `async def api_text_command(payload)`
- [`L905-L913`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L905-L913) `async def list_voice_samples()`
- [`L916-L1811`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L916-L1811) `class LiveBridgeSession` — *Quản lý kết nối giữa 1 tab trình duyệt và phiên Gemini 3.8 Live.*
  - [`L919-L943`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L919-L943) `def __init__(ws)`
  - [`L945-L960`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L945-L960) `async def send_ws_json(payload)`
  - [`L962-L968`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L962-L968) `def _reset_turn_metrics(anchor_ts)`
  - [`L970-L996`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L970-L996) `async def _sync_rules_context_to_gemini(event_note, send_to_model)` — *Cập nhật tức thì bảng Từ, Khẩu lệnh, Luật IF-ELSE và 2 Bể lên giao diện (và Gemini nếu cần).*
  - [`L998-L1031`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L998-L1031) `async def _run_voice_enrollment_sequence(duration_seconds, target_tier, target_name)` — *Thực thi chuỗi tín hiệu phần cứng khi bắt đầu thu âm cấp quyền:*
  - [`L1033-L1100`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1033-L1100) `async def _process_completed_voice_enrollment(pcm_bytes)` — *Xử lý sau khi thu âm đủ: Nháy đèn báo kết thúc -> Báo thu âm đủ -> Phân tích tần số -> Báo phân tích xong & hỏi tên.*
  - [`L1102-L1351`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1102-L1351) `async def handle_tool_call(fc)`
  - [`L1353-L1482`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1353-L1482) `async def gemini_receive_loop()` — *Nhận liên tục các sự kiện từ Gemini 3.8 Live và đẩy về giao diện.*
  - [`L1484-L1614`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1484-L1614) `async def stream_wav_sample(sample_id)`
  - [`L1616-L1799`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1616-L1799) `async def run()`
  - [`L1801-L1811`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1801-L1811) `async def _periodic_timer_sync()`
- [`L1815-L1818`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1815-L1818) `async def websocket_endpoint(ws)`

### 📄 [`simulator/rule_engine.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py)
- [`L39-L40`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L39-L40) `def get_vn_now()`
- [`L43-L45`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L43-L45) `def format_vn_time_ampm(dt)`
- [`L203-L210`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L203-L210) `def _format_clock_12h(hour_24, minute, second)`
- [`L213-L299`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L213-L299) `def _extract_vn_date(time_str, date_str, now_vn)` — *Tách thông tin ngày/tháng (nếu người dùng có nói rõ) ra khỏi chuỗi giờ.*
- [`L318-L341`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L318-L341) `def detect_repeat_mode(text, explicit_repeat)` — *Tự động nhận diện chu kỳ lặp nếu người dùng nói 'hàng ngày', 'hàng tuần', 'hàng giờ', 'hàng tháng'.*
- [`L344-L364`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L344-L364) `def normalize_reset_scope(raw_scope)` — *Chuẩn hóa 4 loại Reset:*
- [`L367-L455`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L367-L455) `def parse_vn_clock_and_date(time_str, date_str, repeat, now_vn)` — *Phân tích chuỗi giờ Việt Nam theo đúng 4 quy tắc của Sếp + chu kỳ lặp (1 lần vs hàng ngày/tuần):*
- [`L458-L464`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L458-L464) `def parse_vn_time_string(time_str)` — *Hàm tương thích ngược trả về (hh, mm, ss) của mốc đầu tiên.*
- [`L467-L477`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L467-L477) `def ensure_factory_file()` — *Mặc định gốc hoàn toàn nguyên bản: mở cửa chỉ mở cửa, bật đèn chỉ bật đèn (không có luật phụ).*
- [`L480-L3130`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L480-L3130) `class SmartHomeEngine`
  - [`L481-L504`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L481-L504) `def __init__(on_event, on_voice_reset)`
  - [`L507-L544`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L507-L544) `def system_policies()`
  - [`L547-L548`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L547-L548) `def query_permission_mode()`
  - [`L550-L582`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L550-L582) `async def set_query_permission_policy(mode)` — *Thay đổi quy tắc phân quyền hỏi đáp (CHỈ Cấp 1 Nguyễn Tuấn Anh mới có quyền thay đổi):*
  - [`L584-L735`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L584-L735) `async def admin_update_system_policy(policy_key, policy_value, target_device_id)` — *Cho phép Admin Cấp 1 (Nguyễn Tuấn Anh) sửa BẤT KỲ quy tắc hệ thống, quyền hạn của Cấp 2/Cấp 3,*
  - [`L737-L747`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L737-L747) `def _init_users()`
  - [`L750-L751`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L750-L751) `def current_user_id()`
  - [`L754-L768`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L754-L768) `def current_tier()`
  - [`L770-L774`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L770-L774) `def get_current_user_name()`
  - [`L781-L809`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L781-L809) `def current_role(val)`
  - [`L811-L827`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L811-L827) `def set_active_user(user_or_role)`
  - [`L829-L841`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L829-L841) `def _default_overlay()`
  - [`L843-L866`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L843-L866) `def _load_overlay()`
  - [`L868-L876`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L868-L876) `def _get_user_pool(user_id)`
  - [`L878-L885`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L878-L885) `def _save_overlay()`
  - [`L887-L889`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L887-L889) `async def emit(event)`
  - [`L891-L898`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L891-L898) `def get_merged_aliases(user_id)`
  - [`L900-L904`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L900-L904) `def get_word_mappings(user_id)`
  - [`L906-L910`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L906-L910) `def get_if_else_rules(user_id)`
  - [`L912-L913`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L912-L913) `def get_chains()`
  - [`L915-L927`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L915-L927) `def format_duration_vi(total_sec)`
  - [`L929-L945`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L929-L945) `def _action_device_phrase_vi(device_id, action)`
  - [`L947-L988`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L947-L988) `def describe_device_command(device_id)` — *Trả lời ngắn gọn lệnh điều khiển hiện tại của một thiết bị (gồm mặc định, từ đổi, khẩu lệnh đổi và luật IF).*
  - [`L990-L1136`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L990-L1136) `def get_pools_summary(query_type, target_device_id)` — *Trả về thông tin chi tiết của 2 Bể (Bể Hẹn Giờ & Bể Luật Động) hoặc lệnh của 1 thiết bị.*
  - [`L1138-L1190`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1138-L1190) `def get_snapshot()`
  - [`L1192-L1206`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1192-L1206) `def check_permission(required_role)`
  - [`L1208-L1254`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1208-L1254) `def _check_custom_directive_device_lock(dev_id)` — *Kiểm tra xem có quy định tự nhiên nào của Admin Cấp 1 (trong custom_system_directives)*
  - [`L1256-L1274`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1256-L1274) `def check_device_permission(dev_id)`
  - [`L1279-L1292`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1279-L1292) `def _find_or_slug_user(target_name)`
  - [`L1294-L1331`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1294-L1331) `async def blink_signal_light(device_id, pulse_sec)` — *Nháy đèn 1 phát (Bật -> Tắt hoặc Tắt -> Bật) để làm tín hiệu bắt đầu/kết thúc thu âm cấp quyền.*
  - [`L1333-L1396`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1333-L1396) `async def start_voice_enrollment(target_tier, target_name, duration_seconds, duration_sec)` — *Bước 1 của Thu âm cấp quyền giọng nói:*
  - [`L1398-L1448`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1398-L1448) `async def stage_voice_enrollment_analysis(f0_hz, centroid_hz, embedding, duration_sec)` — *Bước 2 của Thu âm cấp quyền: Sau khi thu âm đủ -> Báo đã thu âm đủ, đã phân tích xong -> Hỏi tên (hoặc lưu luôn nếu đã có tên).*
  - [`L1450-L1496`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1450-L1496) `async def finalize_voice_enrollment(target_name, target_tier)` — *Bước 3 của Thu âm cấp quyền: Gán tên cho người vừa thu âm phân tích xong và lưu quyền chính thức.*
  - [`L1498-L1568`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1498-L1568) `async def grant_user_permission(target_name, target_tier)` — *Cấp quyền theo 3 Tầng (Tôn trọng cấu hình động `system_policies` do Admin Cấp 1 thiết lập).*
  - [`L1570-L1623`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1570-L1623) `async def revoke_user_permission(target_name)` — *Hủy quyền theo 3 Tầng (Tôn trọng cấu hình động `system_policies` do Admin Cấp 1 thiết lập).*
  - [`L1625-L1646`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1625-L1646) `def _expand_targets(device_id, action)`
  - [`L1648-L1654`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1648-L1654) `def _state_verb_vi(dev_type, state, already)`
  - [`L1656-L1691`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1656-L1691) `def _build_concise_spoken_reply(results)`
  - [`L1693-L1830`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1693-L1830) `async def execute_device_action(device_id, action, source, bypass_rbac, trigger_chains)`
  - [`L1832-L1842`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1832-L1842) `async def sync_edge_flash()` — *Đồng bộ bản sao 2 Bể (Bể 1 Hẹn giờ & Bể 2 Luật IF-ELSE) xuống Flash LittleFS của ESP8266.*
  - [`L1844-L1864`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1844-L1864) `async def update_sensor_telemetry(temp_c, humidity_pct, wifi_rssi_dbm)` — *Cập nhật thông số cảm biến DHT11 từ mạch ESP8266 và tự động kiểm tra luật ngưỡng nhiệt độ/độ ẩm.*
  - [`L1866-L1903`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1866-L1903) `async def update_soil_moisture_telemetry(soil_moisture_pct, auto_pump_below_pct, auto_stop_above_pct)` — *Cập nhật thông số cảm biến Độ ẩm Đất YL-69 (Chân A0) và tự động điều khiển Máy bơm tưới cây (Chân D3).*
  - [`L1905-L1920`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1905-L1920) `async def learn_ir_remote_command(device_name, command_action, protocol, hex_code)` — *Chiếm quyền / Học lệnh Remote Hồng ngoại 38kHz (VS1838B D5 -> Lưu Write-Through -> Phát IR LED D2).*
  - [`L1922-L2001`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1922-L2001) `async def _evaluate_reactive_if_else(changed_dev_id, new_state)` — *Kiểm tra luật IF khi `changed_dev_id` chuyển sang `new_state`.*
  - [`L2006-L2026`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2006-L2026) `def _check_t1_timer_conflict(device_id, new_fire_at)` — *Kiểm tra xem cấp dưới có đặt lệnh vướng vào khung giờ hẹn giờ của Tầng 1 Nguyễn Tuấn Anh hay không.*
  - [`L2028-L2122`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2028-L2122) `async def schedule_timer_flexible(device_id, action, hours, minutes, seconds, vn_time_ampm, vn_date, repeat, reason)`
  - [`L2124-L2243`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2124-L2243) `async def schedule_action(device_id, action, delay_seconds, reason, bypass_rbac, trigger_chains, target_vn_time, repeat)`
  - [`L2245-L2334`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2245-L2334) `async def update_or_cancel_timer(device_id, operation, new_action, hours, minutes, seconds, vn_time_ampm, vn_date, repeat)`
  - [`L2339-L2389`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2339-L2389) `async def set_word_mapping(custom_word, target_meaning, require_confirmation)`
  - [`L2391-L2464`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2391-L2464) `async def create_alias_rule(phrase, target_devices_csv, target_actions_csv, require_confirmation)`
  - [`L2466-L2516`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2466-L2516) `async def set_server_connection_mode(connected)` — *Chuyển đổi giữa Chế độ Kết nối Server Laptop (Online) và Chế độ Mạch Độc Lập (Offline Default):*
  - [`L2518-L2636`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2518-L2636) `async def execute_offline_default_command(text, source)` — *Bộ giải mã Lệnh Mặc Định Cơ Bản khi Mạch chạy Độc Lập không kết nối Server (Offline Mode):*
  - [`L2638-L2680`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2638-L2680) `async def execute_alias_rule(phrase)`
  - [`L2682-L2709`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2682-L2709) `def _has_cycle(rules)`
  - [`L2711-L2726`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2711-L2726) `def _check_t1_rule_conflict(new_rule)` — *Kiểm tra xem luật IF-ELSE của Tầng 2 có mâu thuẫn hoặc vướng luật ưu tiên của Tầng 1 Nguyễn Tuấn Anh hay không.*
  - [`L2728-L2861`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2728-L2861) `async def set_if_else_rule(when_device_id, when_state, then_device_id, then_action, delay_seconds, else_device_id, else_action, evaluate_now, require_confirmation)`
  - [`L2863-L2914`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2863-L2914) `async def confirm_pending_action(confirmed)` — *Xác nhận hoặc hủy hành động đang chờ (bao gồm cả Xét Luật mới lẫn Reset Hệ Thống).*
  - [`L2923-L2973`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2923-L2973) `async def request_factory_reset(scope)` — *Bước 1: Khi người dùng nói 'Reset ...', chưa xóa ngay mà bật cờ chờ xác nhận đúng theo loại reset và tầng.*
  - [`L2975-L2997`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2975-L2997) `async def confirm_factory_reset(confirmed)` — *Bước 2: Thực thi hoặc hủy Reset (hoặc Luật đang chờ) sau khi người dùng trả lời câu hỏi xác nhận.*
  - [`L2999-L3130`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2999-L3130) `async def factory_reset(scope)`

### 📄 [`simulator/mqtt_bridge.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py)
- [`L74-L486`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L74-L486) `class SmartHomeMQTTBridge` — *Bộ điều phối bản tin MQTT chuẩn System Design Primer:*
  - [`L82-L127`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L82-L127) `def __init__(on_event)`
  - [`L129-L139`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L129-L139) `def _load_ir_db()`
  - [`L141-L143`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L141-L143) `def _save_ir_db_write_through()` — *Write-Through Cache: Cập nhật RAM đồng thời ghi xuyên suốt xuống đĩa.*
  - [`L145-L180`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L145-L180) `async def publish(topic, payload, qos, retain, direction)` — *Phát hành gói tin MQTT với cơ chế kiểm soát Back Pressure.*
  - [`L182-L257`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L182-L257) `async def publish_actuate_command(device_id, state, action, source, user_name, tier)` — *Xuất bản tin MQTT điều khiển phần cứng ESP8266 (`smarthome/cmd/actuate`)*
  - [`L259-L274`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L259-L274) `async def publish_enrollment_blink(device_id, pulse_ms)` — *Xuất bản tin MQTT `smarthome/cmd/enroll_blink` để ESP8266 nháy đèn báo hiệu bắt đầu thu âm 3-2-1.*
  - [`L276-L321`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L276-L321) `async def sync_pools_to_esp8266_flash(timers, if_else_rules, system_policies)` — *CAP Theorem (AP Failover): Đồng bộ bản sao Bể 1 (Hẹn giờ) và Bể 2 (Luật IF-ELSE)*
  - [`L323-L350`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L323-L350) `async def update_dht11_telemetry(temp_c, humidity_pct, wifi_rssi_dbm)` — *Nhận bản tin cảm biến `smarthome/telemetry/dht11` từ chân D6 của ESP8266.*
  - [`L352-L379`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L352-L379) `async def update_soil_moisture_telemetry(soil_moisture_pct, adc_raw)` — *Nhận bản tin cảm biến Độ ẩm Đất `smarthome/telemetry/soil_moisture` từ chân A0 (YL-69 + LM393).*
  - [`L381-L405`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L381-L405) `async def start_ir_learning(device_name, command_action)` — *Bật chế độ Học lệnh chiếm quyền Remote (`smarthome/ir/learn_start`) trên chân D5 (`VS1838B`).*
  - [`L407-L471`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L407-L471) `async def complete_ir_learning(protocol, hex_code, raw_timings_us)` — *Nhận kết quả giải mã xung hồng ngoại từ ESP8266 (`smarthome/ir/learned_result`) và lưu Write-Through.*
  - [`L473-L486`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L473-L486) `def get_summary()`

### 📄 [`simulator/voice_auth.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py)
- [`L31-L132`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L31-L132) `def extract_voice_features(pcm16, sr)` — *Trích xuất tần số cơ bản F0 (Hz), Spectral Centroid (Hz), dải trầm Liveness và Vector 26 chiều.*
- [`L135-L142`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L135-L142) `def cosine_sim(v1, v2)`
- [`L145-L177`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L145-L177) `def transform_pcm_to_intruder_voice(pcm16, sr)` — *Biến đổi tần số giọng nói gốc thành Giọng số 2 (Giọng người lạ - Không được phép):*
- [`L180-L446`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L180-L446) `class VoiceAuthManager` — *Quản lý hồ sơ Giọng 1 (Được phép - Chủ nhà) vs Giọng 2 (Không được phép)*
  - [`L185-L199`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L185-L199) `def __init__(audio_dir)`
  - [`L201-L253`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L201-L253) `def _init_or_load_profiles()` — *Tạo sẵn 2 giọng nói WAV 16kHz (Giọng 1: Được phép, Giọng 2: Không được phép) từ mẫu âm thanh.*
  - [`L255-L282`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L255-L282) `def enroll_owner_from_pcm16k(pcm_bytes, label)` — *Đăng ký vân giọng mới từ đoạn thu âm tự do 5 - 10 giây (16kHz PCM).*
  - [`L284-L304`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L284-L304) `def analyze_voice_pcm16k(pcm_bytes)` — *Phân tích đoạn thu âm giọng nói 16kHz vừa thu được để chuẩn bị cấp quyền.*
  - [`L306-L341`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L306-L341) `def register_enrolled_user_profile(user_id, user_name, tier, role, f0_hz, centroid_hz, embedding)` — *Lưu hồ sơ giọng nói của người dùng mới được cấp quyền (Cấp 2 hoặc Cấp 3).*
  - [`L343-L407`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L343-L407) `def verify_pcm16k_and_apply_strikes(pcm_bytes)` — *Phân tích tần số giọng nói từ luồng PCM 16kHz và áp dụng quy tắc chặn 2 lần rồi im lặng.*
  - [`L409-L411`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L409-L411) `def reset_strikes()`
  - [`L413-L446`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L413-L446) `def reset_to_owner_only()` — *Reset quyền giọng nói: Xóa mọi giọng phụ khác, chỉ giữ lại duy nhất giọng của Chủ nhà (owner_voice_1) và mẫu đối chứng.*

### 📄 [`simulator/knowledge_rag.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py)
- [`L102-L112`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L102-L112) `def ensure_kb_file()`
- [`L115-L317`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L115-L317) `class SmartHomeKnowledgeRAG` — *Bộ RAG sử dụng Google Embedding (`gemini-embedding-001`) để trả lời ngắn gọn về trợ lý ảo và quy định 3 tầng.*
  - [`L118-L123`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L118-L123) `def __init__(api_key)`
  - [`L125-L126`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L125-L126) `def _doc_text_for_embedding(item)`
  - [`L128-L168`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L128-L168) `def _load_or_build_embeddings()`
  - [`L171-L177`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L171-L177) `def _cosine(a, b)`
  - [`L179-L256`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L179-L256) `def retrieve(query, current_tier, query_permission_mode, top_k)` — *Truy xuất đoạn tri thức khớp nhất bằng Google Embedding (`gemini-embedding-001`) + Cosine Similarity.*
  - [`L258-L313`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L258-L313) `def upsert_knowledge_item(topic, content, keywords, min_tier, current_tier)` — *Cho phép Admin Cấp 1 (Nguyễn Tuấn Anh) dạy thêm hoặc sửa nội dung RAG bằng giọng nói và nhúng vector ngay.*
  - [`L315-L317`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L315-L317) `def reset_custom_knowledge()`

